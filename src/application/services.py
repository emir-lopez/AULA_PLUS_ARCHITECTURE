"""Application Services (Service Layer). Un método = un caso de uso.

Los servicios abren la Unit of Work, obtienen los Aggregates, entregan la hora
actual, invocan al dominio y confirman. No contienen reglas de negocio: esas
viven en ``domain`` (SRP). Las dependencias llegan por constructor (DIP).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from domain.agenda import AgendaTutor
from domain.exceptions import ConflictoDeRecurso
from domain.policies import (
    CalculadoraReembolso,
    ParametrosOperacion,
    PoliticaCompensacion,
    PoliticaSuspension,
)
from domain.sede import Sede
from domain.sesion import TransaccionSesion
from domain.specifications import SolicitudDeReserva
from domain.value_objects import (
    Calificacion,
    Dinero,
    EvidenciaAsistencia,
    Modalidad,
    ParteSesion,
    VentanaHoraria,
)

from .ports import Reloj, UnidadDeTrabajo

FabricaUnidadDeTrabajo = Callable[[], UnidadDeTrabajo]


@dataclass(frozen=True)
class SolicitudReserva:
    sesion_id: str
    estudiante_id: str
    tutor_id: str
    bloque_id: str
    modalidad: Modalidad = Modalidad.EN_LINEA
    sede_id: str | None = None


@dataclass
class Politicas:
    params: ParametrosOperacion = field(default_factory=ParametrosOperacion)
    reembolso: CalculadoraReembolso = field(default_factory=CalculadoraReembolso)
    compensacion: PoliticaCompensacion = field(default_factory=PoliticaCompensacion)
    suspension: PoliticaSuspension = field(default_factory=PoliticaSuspension)


class _ServicioBase:
    def __init__(self, fabrica_uow: FabricaUnidadDeTrabajo, reloj: Reloj, politicas: Politicas | None = None):
        self.fabrica_uow = fabrica_uow
        self.reloj = reloj
        self.politicas = politicas or Politicas()

    def _ahora(self) -> datetime:
        return self.reloj.ahora()


class ServicioAgendaTutor(_ServicioBase):
    """Registro de tutores, bloques y sedes (NB-02). Prerrequisito de CU-01."""

    def registrar_tutor(self, tutor_id: str, nombre: str, tarifa_hora: Dinero) -> AgendaTutor:
        agenda = AgendaTutor(tutor_id, nombre, str(tarifa_hora.monto), self._ahora())
        with self.fabrica_uow() as uow:
            uow.agendas.agregar(agenda)
            uow.confirmar()
        return agenda

    def agregar_bloque(self, tutor_id: str, bloque_id: str, ventana: VentanaHoraria) -> AgendaTutor:
        with self.fabrica_uow() as uow:
            agenda = uow.agendas.obtener_del_tutor(tutor_id)
            agenda.agregar_bloque(bloque_id, ventana, self._ahora())
            uow.agendas.guardar(agenda)
            uow.confirmar()
        return agenda

    def publicar_disponibilidad(self, tutor_id: str, bloques: list[tuple[str, VentanaHoraria]]) -> int:
        """Publica varios bloques en una sola transacción; devuelve cuántos eran nuevos."""
        with self.fabrica_uow() as uow:
            agenda = uow.agendas.obtener_del_tutor(tutor_id)
            agregados = agenda.publicar_disponibilidad(bloques, self._ahora())
            uow.agendas.guardar(agenda)
            uow.confirmar()
        return agregados

    def registrar_sede(self, sede: Sede) -> Sede:
        with self.fabrica_uow() as uow:
            uow.sedes.agregar(sede)
            uow.confirmar()
        return sede


class ServicioReservaSesion(_ServicioBase):
    """CU-01 y CU-02."""

    def reservar_sesion(self, solicitud: SolicitudReserva) -> TransaccionSesion:
        ahora = self._ahora()
        with self.fabrica_uow() as uow:
            agenda = uow.agendas.obtener_del_tutor(solicitud.tutor_id)
            bloque = agenda.bloque(solicitud.bloque_id)
            ocupacion = cupo = 0
            if solicitud.modalidad == Modalidad.PRESENCIAL and solicitud.sede_id:
                sede = uow.sedes.obtener_para_reserva(solicitud.sede_id)  # bloquea la fila (H-06)
                cupo = sede.cupo_maximo
                ocupacion = uow.transacciones.contar_ocupacion_sede(sede.sede_id, bloque.ventana)
            candidato = SolicitudDeReserva(
                inicio_sesion=bloque.ventana.inicio, ahora=ahora,
                agenda_actualizada_en=agenda.actualizada_en, tutor_suspendido=agenda.suspendido,
                bloque_disponible=agenda.bloque_esta_disponible(solicitud.bloque_id),
                es_presencial=solicitud.modalidad == Modalidad.PRESENCIAL,
                ocupacion_sede=ocupacion, cupo_sede=cupo,
            )
            horas = Decimal(int(bloque.ventana.duracion.total_seconds())) / Decimal(3600)
            monto = Dinero(Decimal(agenda.tarifa_hora) * horas)
            sesion = TransaccionSesion.reservar(
                sesion_id=solicitud.sesion_id, estudiante_id=solicitud.estudiante_id,
                tutor_id=solicitud.tutor_id, bloque_id=solicitud.bloque_id, ventana=bloque.ventana,
                modalidad=solicitud.modalidad, monto=monto, solicitud=candidato,
                params=self.politicas.params, sede_id=solicitud.sede_id,
            )
            agenda.congelar_bloque(solicitud.bloque_id, sesion.sesion_id, ahora)
            uow.transacciones.agregar(sesion)
            uow.agendas.guardar(agenda)
            uow.confirmar()
        return sesion

    def confirmar_pago_reserva(self, sesion_id: str, monto_pagado: Dinero) -> TransaccionSesion:
        ahora = self._ahora()
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            agenda = uow.agendas.obtener_del_tutor(sesion.tutor_id)
            sesion.confirmar_pago(monto_pagado, ahora)
            agenda.bloquear_bloque(sesion.bloque_id, sesion.sesion_id, ahora)
            uow.transacciones.guardar(sesion)
            uow.agendas.guardar(agenda)
            uow.confirmar()
        return sesion

    def registrar_pago_fallido(self, sesion_id: str, motivo: str) -> TransaccionSesion:
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            sesion.registrar_pago_fallido(motivo, self._ahora())
            uow.transacciones.guardar(sesion)
            uow.confirmar()
        return sesion

    def expirar_congelamiento(self, sesion_id: str) -> bool:
        ahora = self._ahora()
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            if not sesion.expirar_congelamiento(ahora):
                return False
            agenda = uow.agendas.obtener_del_tutor(sesion.tutor_id)
            agenda.liberar_bloque(sesion.bloque_id, sesion.sesion_id, ahora)
            uow.transacciones.guardar(sesion)
            uow.agendas.guardar(agenda)
            uow.confirmar()
        return True


class ServicioCancelacionSesion(_ServicioBase):
    """CU-03 (estudiante) y cancelación del tutor (US-08, US-09)."""

    def cancelar_por_estudiante(self, sesion_id: str, estudiante_id: str) -> TransaccionSesion:
        ahora = self._ahora()
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            agenda = uow.agendas.obtener_del_tutor(sesion.tutor_id)
            sesion.cancelar_por_estudiante(estudiante_id, ahora, self.politicas.reembolso)
            agenda.liberar_bloque(sesion.bloque_id, sesion.sesion_id, ahora)
            uow.transacciones.guardar(sesion)
            uow.agendas.guardar(agenda)
            uow.confirmar()
        return sesion

    def cancelar_por_tutor(self, sesion_id: str, tutor_id: str) -> TransaccionSesion:
        ahora = self._ahora()
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            agenda = uow.agendas.obtener_del_tutor(sesion.tutor_id)
            _, tardia = sesion.cancelar_por_tutor(tutor_id, ahora, self.politicas.compensacion)
            agenda.liberar_bloque(sesion.bloque_id, sesion.sesion_id, ahora)
            if tardia:
                agenda.registrar_incumplimiento("CancelacionTardia", ahora, self.politicas.suspension)
            uow.transacciones.guardar(sesion)
            uow.agendas.guardar(agenda)
            uow.confirmar()
        return sesion


class ServicioEjecucionSesion(_ServicioBase):
    """Evidencia de asistencia, No-Show y calificación (NB-01, NB-13; H-15 cerrado)."""

    def completar_sesion(self, sesion_id: str, evidencia: EvidenciaAsistencia) -> TransaccionSesion:
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            sesion.completar_con_evidencia(evidencia, self._ahora())
            uow.transacciones.guardar(sesion)
            uow.confirmar()
        return sesion

    def registrar_no_show(self, sesion_id: str, parte_ausente: ParteSesion) -> TransaccionSesion:
        ahora = self._ahora()
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            sesion.registrar_no_show(parte_ausente, ahora, self.politicas.params, self.politicas.compensacion)
            uow.transacciones.guardar(sesion)
            if parte_ausente == ParteSesion.TUTOR:
                agenda = uow.agendas.obtener_del_tutor(sesion.tutor_id)
                agenda.registrar_incumplimiento("NoShow", ahora, self.politicas.suspension)
                uow.agendas.guardar(agenda)
            uow.confirmar()
        return sesion

    def extender_sesion(self, sesion_id: str, estudiante_id: str, minutos: int,
                        monto_pagado: Dinero) -> TransaccionSesion:
        """US-12: cobra la extensión dentro de la plataforma y alarga el bloque del tutor en la misma transacción."""
        ahora = self._ahora()
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            agenda = uow.agendas.obtener_del_tutor(sesion.tutor_id)
            sesion.extender(estudiante_id, minutos, Dinero(agenda.tarifa_hora), monto_pagado, ahora,
                            self.politicas.params.minutos_maximos_extension)
            agenda.extender_bloque(sesion.bloque_id, sesion.sesion_id, sesion.ventana)
            uow.transacciones.guardar(sesion)
            uow.agendas.guardar(agenda)
            uow.confirmar()
        return sesion

    def reportar_falla_conexion(self, sesion_id: str, solicitante_id: str) -> TransaccionSesion:
        """US-13: registra la caída y la deja visible para Soporte."""
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            sesion.reportar_falla_conexion(solicitante_id, self._ahora())
            uow.transacciones.guardar(sesion)
            uow.confirmar()
        return sesion

    def registrar_reconexion(self, sesion_id: str) -> TransaccionSesion:
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            sesion.registrar_reconexion(self._ahora(), self.politicas.params)
            uow.transacciones.guardar(sesion)
            uow.confirmar()
        return sesion

    def calificar(self, sesion_id: str, estudiante_id: str, calificacion: Calificacion) -> TransaccionSesion:
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            sesion.calificar(estudiante_id, calificacion, self._ahora())
            uow.transacciones.guardar(sesion)
            uow.confirmar()
        return sesion


class ServicioDisputaSesion(_ServicioBase):
    """CU-04 y resolución por Soporte."""

    def abrir_disputa(self, sesion_id: str, solicitante_id: str, motivo: str) -> TransaccionSesion:
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            sesion.abrir_disputa(solicitante_id, motivo, self._ahora(), self.politicas.params)
            uow.transacciones.guardar(sesion)
            uow.confirmar()
        return sesion

    def resolver(self, sesion_id: str, a_favor_de: ParteSesion, resolucion: str) -> TransaccionSesion:
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            sesion.resolver_revision(a_favor_de, resolucion, self._ahora())
            uow.transacciones.guardar(sesion)
            uow.confirmar()
        return sesion


class ServicioLiquidacionPago(_ServicioBase):
    """CU-05."""

    def liberar_pago_al_tutor(self, sesion_id: str) -> TransaccionSesion:
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            sesion.liberar_fondos(self._ahora(), self.politicas.params)
            uow.transacciones.guardar(sesion)
            uow.confirmar()
        return sesion

    def liberar_pendientes(self, ids: list[str]) -> list[str]:
        """Proceso batch: libera los pagos que la Query de lectura reporta como listos."""
        liberados = []
        for sesion_id in ids:
            try:
                self.liberar_pago_al_tutor(sesion_id)
                liberados.append(sesion_id)
            except ConflictoDeRecurso:
                continue
        return liberados
