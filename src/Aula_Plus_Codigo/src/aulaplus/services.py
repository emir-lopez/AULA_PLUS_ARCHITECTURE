"""Service Layer: coordina casos de uso y deja las reglas al dominio."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .domain import (
    DecisionPendiente, Dinero, EstadoSesion, PoliticaReembolso,
    PoliticaRetencion, ReglaDeNegocio, TransaccionSesion,
)
from .ports import Reloj, UnidadDeTrabajo

FabricaUnidadDeTrabajo = Callable[[], UnidadDeTrabajo]


@dataclass(frozen=True)
class SolicitudReserva:
    sesion_id: str
    estudiante_id: str
    tutor_id: str
    bloque_id: str
    monto: Dinero
    modalidad: str = "EnLinea"


@dataclass(frozen=True)
class ResultadoReserva:
    sesion_id: str
    estado: str
    congelado_hasta: str
    monto: str


class ServicioReservaSesion:
    def __init__(self, fabrica_uow: FabricaUnidadDeTrabajo, reloj: Reloj):
        self.fabrica_uow = fabrica_uow
        self.reloj = reloj

    def reservar_sesion(self, solicitud: SolicitudReserva) -> ResultadoReserva:
        # H-06: falta capacidad de sede con control atómico. El código base
        # demuestra el flujo en línea sin inventar la política presencial.
        if solicitud.modalidad != "EnLinea":
            raise DecisionPendiente("H-06: cupo presencial pendiente de diseño")
        ahora = self.reloj.ahora()
        with self.fabrica_uow() as uow:
            agenda = uow.agendas.obtener_del_tutor(solicitud.tutor_id)
            try:
                bloque = agenda.bloques[solicitud.bloque_id]
            except KeyError as exc:
                raise ReglaDeNegocio("HorarioNoDisponible") from exc
            sesion = TransaccionSesion.reservar(
                solicitud.sesion_id, solicitud.estudiante_id, solicitud.tutor_id,
                solicitud.bloque_id, bloque.ventana, solicitud.monto, ahora,
            )
            agenda.congelar_bloque(solicitud.bloque_id, sesion.sesion_id, ahora)
            uow.transacciones.agregar(sesion)
            uow.agendas.guardar(agenda)
            uow.confirmar()
        return ResultadoReserva(sesion.sesion_id, sesion.estado.value,
                                sesion.congelado_hasta.isoformat(), str(sesion.monto.monto))

    def confirmar_pago_reserva(self, sesion_id: str, monto_pagado: Dinero) -> str:
        # La pasarela ya confirmó el cobro. H-11: cobros tardíos necesitan
        # compensación externa; este código rechaza la transición local.
        ahora = self.reloj.ahora()
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            agenda = uow.agendas.obtener_del_tutor(sesion.tutor_id)
            sesion.confirmar_pago(monto_pagado, ahora)
            agenda.bloquear_bloque(sesion.bloque_id, sesion.sesion_id)
            uow.transacciones.guardar(sesion)
            uow.agendas.guardar(agenda)
            uow.confirmar()
        return sesion.estado.value

    def expirar_congelamiento(self, sesion_id: str) -> bool:
        ahora = self.reloj.ahora()
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            if not sesion.expirar_congelamiento(ahora):
                return False
            agenda = uow.agendas.obtener_del_tutor(sesion.tutor_id)
            agenda.liberar_bloque(sesion.bloque_id, sesion.sesion_id)
            uow.transacciones.guardar(sesion)
            uow.agendas.guardar(agenda)
            uow.confirmar()
        return True


class ServicioCancelacionSesion:
    def __init__(self, fabrica_uow: FabricaUnidadDeTrabajo, reloj: Reloj,
                 politica: PoliticaReembolso):
        self.fabrica_uow, self.reloj, self.politica = fabrica_uow, reloj, politica

    def cancelar_sesion_por_estudiante(self, sesion_id: str, estudiante_id: str) -> Dinero:
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            agenda = uow.agendas.obtener_del_tutor(sesion.tutor_id)
            reembolso = sesion.cancelar_por_estudiante(estudiante_id, self.reloj.ahora(), self.politica)
            agenda.liberar_bloque(sesion.bloque_id, sesion.sesion_id)
            uow.transacciones.guardar(sesion)
            uow.agendas.guardar(agenda)
            uow.confirmar()
        return reembolso


class ServicioDisputaSesion:
    def __init__(self, fabrica_uow: FabricaUnidadDeTrabajo):
        self.fabrica_uow = fabrica_uow

    def abrir_disputa(self, sesion_id: str, solicitante_id: str, motivo: str) -> str:
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            sesion.abrir_disputa(solicitante_id, motivo)
            uow.transacciones.guardar(sesion)
            uow.confirmar()
        return sesion.estado.value


class ServicioLiquidacionPago:
    def __init__(self, fabrica_uow: FabricaUnidadDeTrabajo, reloj: Reloj,
                 politica: PoliticaRetencion):
        self.fabrica_uow, self.reloj, self.politica = fabrica_uow, reloj, politica

    def liberar_pago_al_tutor(self, sesion_id: str) -> tuple[Dinero, Dinero]:
        with self.fabrica_uow() as uow:
            sesion = uow.transacciones.obtener(sesion_id)
            desglose = sesion.liberar_fondos(self.reloj.ahora(), self.politica)
            uow.transacciones.guardar(sesion)
            uow.confirmar()
        return desglose
