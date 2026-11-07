"""Repositories SQLAlchemy: cargan y guardan Aggregates completos (sin repositorio por entidad interna).

El control de concurrencia es optimista: cada guardado exige que la versión en la
base sea la misma que se leyó; si otro proceso guardó antes, se lanza
ConflictoDeRecurso (HTTP 409) y la Unit of Work revierte.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from domain.agenda import AgendaTutor, BloqueDeAgenda
from domain.exceptions import ConflictoDeRecurso, RecursoNoEncontrado
from domain.sede import Sede
from domain.sesion import Disputa, TransaccionSesion
from domain.state_machine import EstadoBloque, EstadoPago, EstadoSesion
from domain.value_objects import (
    Calificacion,
    DesgloseFinanciero,
    Dinero,
    Modalidad,
    ParteSesion,
    PorcentajeComision,
    VentanaHoraria,
)

from .db import AgendaRow, BloqueRow, SedeRow, SesionRow, a_utc

ESTADOS_QUE_OCUPAN_CUPO = (EstadoSesion.RESERVADA.value, EstadoSesion.CONFIRMADA.value)


class Rastreador:
    """Recuerda los Aggregates tocados para que la UoW extraiga sus eventos al confirmar."""

    def __init__(self) -> None:
        self.vistos: list = []

    def recordar(self, agregado: object) -> None:
        if all(agregado is not otro for otro in self.vistos):
            self.vistos.append(agregado)


class RepositorioSqlAgendaTutor:
    def __init__(self, session: Session, rastreador: Rastreador):
        self.session, self.rastreador = session, rastreador

    def obtener_del_tutor(self, tutor_id: str) -> AgendaTutor:
        fila = self.session.get(AgendaRow, tutor_id)
        if fila is None:
            raise RecursoNoEncontrado("TutorNoEncontrado", f"No existe el tutor {tutor_id}")
        bloques = self.session.scalars(select(BloqueRow).where(BloqueRow.tutor_id == tutor_id)).all()
        agenda = AgendaTutor(
            tutor_id=fila.tutor_id, nombre=fila.nombre, tarifa_hora=fila.tarifa_hora,
            actualizada_en=a_utc(fila.actualizada_en),
            bloques={
                b.bloque_id: BloqueDeAgenda(b.bloque_id, VentanaHoraria(a_utc(b.inicio), a_utc(b.fin)),
                                            EstadoBloque(b.estado), b.sesion_id)
                for b in bloques
            },
            marcas_incumplimiento=fila.marcas_incumplimiento, suspendido=fila.suspendido, version=fila.version,
        )
        self.rastreador.recordar(agenda)
        return agenda

    def agregar(self, agenda: AgendaTutor) -> None:
        if self.session.get(AgendaRow, agenda.tutor_id) is not None:
            raise ConflictoDeRecurso("TutorDuplicado", f"El tutor {agenda.tutor_id} ya existe")
        self.session.add(AgendaRow(
            tutor_id=agenda.tutor_id, nombre=agenda.nombre, tarifa_hora=agenda.tarifa_hora,
            actualizada_en=a_utc(agenda.actualizada_en), marcas_incumplimiento=agenda.marcas_incumplimiento,
            suspendido=agenda.suspendido, version=agenda.version,
        ))
        self.session.flush()
        self._reemplazar_bloques(agenda)
        self.rastreador.recordar(agenda)

    def guardar(self, agenda: AgendaTutor) -> None:
        resultado = self.session.execute(
            update(AgendaRow)
            .where(AgendaRow.tutor_id == agenda.tutor_id, AgendaRow.version == agenda.version)
            .values(actualizada_en=a_utc(agenda.actualizada_en),
                    marcas_incumplimiento=agenda.marcas_incumplimiento,
                    suspendido=agenda.suspendido, version=agenda.version + 1)
        )
        if resultado.rowcount != 1:
            raise ConflictoDeRecurso("ConflictoDeVersion", "La agenda fue modificada por otra operación")
        agenda.version += 1
        self._reemplazar_bloques(agenda)
        self.rastreador.recordar(agenda)

    def _reemplazar_bloques(self, agenda: AgendaTutor) -> None:
        self.session.execute(delete(BloqueRow).where(BloqueRow.tutor_id == agenda.tutor_id))
        for b in agenda.bloques.values():
            self.session.add(BloqueRow(bloque_id=b.bloque_id, tutor_id=agenda.tutor_id,
                                       inicio=a_utc(b.ventana.inicio), fin=a_utc(b.ventana.fin),
                                       estado=b.estado.value, sesion_id=b.sesion_id))
        self.session.flush()


class RepositorioSqlSede:
    def __init__(self, session: Session):
        self.session = session

    def obtener_para_reserva(self, sede_id: str) -> Sede:
        # FOR UPDATE serializa reservas concurrentes sobre la misma sede en PostgreSQL (H-06).
        fila = self.session.scalars(select(SedeRow).where(SedeRow.sede_id == sede_id).with_for_update()).first()
        if fila is None:
            raise RecursoNoEncontrado("SedeNoEncontrada", f"No existe la sede {sede_id}")
        return Sede(fila.sede_id, fila.nombre, fila.cupo_maximo, fila.radio_geocerca_m)

    def agregar(self, sede: Sede) -> None:
        if self.session.get(SedeRow, sede.sede_id) is not None:
            raise ConflictoDeRecurso("SedeDuplicada", f"La sede {sede.sede_id} ya existe")
        self.session.add(SedeRow(sede_id=sede.sede_id, nombre=sede.nombre, cupo_maximo=sede.cupo_maximo,
                                 radio_geocerca_m=sede.radio_geocerca_m))
        self.session.flush()


def _centavos(dinero: Dinero | None) -> int | None:
    return None if dinero is None else dinero.centavos


def _dinero(centavos: int | None) -> Dinero | None:
    return None if centavos is None else Dinero.desde_centavos(centavos)


class RepositorioSqlTransaccionSesion:
    def __init__(self, session: Session, rastreador: Rastreador):
        self.session, self.rastreador = session, rastreador

    def obtener(self, sesion_id: str) -> TransaccionSesion:
        f = self.session.get(SesionRow, sesion_id)
        if f is None:
            raise RecursoNoEncontrado("SesionNoEncontrada", f"No existe la sesión {sesion_id}")
        monto = Dinero.desde_centavos(f.monto_centavos)
        desglose = None
        if f.comision_centavos is not None:
            desglose = DesgloseFinanciero(monto, Dinero.desde_centavos(f.comision_centavos),
                                          Dinero.desde_centavos(f.neto_centavos or 0),
                                          PorcentajeComision(Decimal(f.porcentaje_comision or "0.20")))
        disputa = None
        if f.disputa_motivo is not None:
            disputa = Disputa(f.disputa_motivo, f.disputa_abierta_por or "", a_utc(f.disputa_abierta_en),
                              a_utc(f.disputa_limite), f.disputa_resolucion, a_utc(f.disputa_resuelta_en))
        sesion = TransaccionSesion(
            sesion_id=f.sesion_id, estudiante_id=f.estudiante_id, tutor_id=f.tutor_id, bloque_id=f.bloque_id,
            ventana=VentanaHoraria(a_utc(f.inicio), a_utc(f.fin)), modalidad=Modalidad(f.modalidad),
            monto=monto, congelado_hasta=a_utc(f.congelado_hasta), sede_id=f.sede_id,
            estado=EstadoSesion(f.estado), estado_pago=EstadoPago(f.estado_pago),
            intentos_pago_fallidos=f.intentos_pago_fallidos, desglose=desglose,
            completada_en=a_utc(f.completada_en), monto_reembolso=_dinero(f.reembolso_centavos),
            motivo_revision=f.motivo_revision,
            parte_ausente=ParteSesion(f.parte_ausente) if f.parte_ausente else None,
            disputa=disputa,
            calificacion=(Calificacion(f.calificacion_puntos, f.calificacion_comentario or "")
                          if f.calificacion_puntos else None),
            liberado_en=a_utc(f.liberado_en), minutos_extension=f.minutos_extension or 0,
            falla_conexion_desde=a_utc(f.falla_conexion_desde), version=f.version,
        )
        self.rastreador.recordar(sesion)
        return sesion

    def agregar(self, sesion: TransaccionSesion) -> None:
        if self.session.get(SesionRow, sesion.sesion_id) is not None:
            raise ConflictoDeRecurso("SesionDuplicada", f"La sesión {sesion.sesion_id} ya existe")
        self.session.add(SesionRow(sesion_id=sesion.sesion_id, **self._columnas(sesion), version=sesion.version))
        self.session.flush()
        self.rastreador.recordar(sesion)

    def guardar(self, sesion: TransaccionSesion) -> None:
        resultado = self.session.execute(
            update(SesionRow)
            .where(SesionRow.sesion_id == sesion.sesion_id, SesionRow.version == sesion.version)
            .values(**self._columnas(sesion), version=sesion.version + 1)
        )
        if resultado.rowcount != 1:
            raise ConflictoDeRecurso("ConflictoDeVersion", "La sesión fue modificada por otra operación")
        sesion.version += 1
        self.rastreador.recordar(sesion)

    def contar_ocupacion_sede(self, sede_id: str, ventana: VentanaHoraria) -> int:
        return self.session.scalar(
            select(func.count()).select_from(SesionRow).where(
                SesionRow.sede_id == sede_id,
                SesionRow.estado.in_(ESTADOS_QUE_OCUPAN_CUPO),
                SesionRow.inicio < a_utc(ventana.fin),
                SesionRow.fin > a_utc(ventana.inicio),
            )
        ) or 0

    @staticmethod
    def _columnas(s: TransaccionSesion) -> dict:
        d = s.disputa
        return {
            "estudiante_id": s.estudiante_id, "tutor_id": s.tutor_id, "bloque_id": s.bloque_id,
            "inicio": a_utc(s.ventana.inicio), "fin": a_utc(s.ventana.fin), "modalidad": s.modalidad.value,
            "sede_id": s.sede_id, "monto_centavos": s.monto.centavos, "congelado_hasta": a_utc(s.congelado_hasta),
            "estado": s.estado.value, "estado_pago": s.estado_pago.value,
            "intentos_pago_fallidos": s.intentos_pago_fallidos,
            "comision_centavos": _centavos(s.desglose.comision) if s.desglose else None,
            "neto_centavos": _centavos(s.desglose.neto_tutor) if s.desglose else None,
            "porcentaje_comision": str(s.desglose.porcentaje.valor) if s.desglose else None,
            "completada_en": a_utc(s.completada_en), "reembolso_centavos": _centavos(s.monto_reembolso),
            "motivo_revision": s.motivo_revision,
            "parte_ausente": s.parte_ausente.value if s.parte_ausente else None,
            "disputa_motivo": d.motivo if d else None, "disputa_abierta_por": d.abierta_por if d else None,
            "disputa_abierta_en": a_utc(d.abierta_en) if d else None,
            "disputa_limite": a_utc(d.fecha_limite) if d else None,
            "disputa_resolucion": d.resolucion if d else None,
            "disputa_resuelta_en": a_utc(d.resuelta_en) if d else None,
            "calificacion_puntos": s.calificacion.puntos if s.calificacion else None,
            "calificacion_comentario": s.calificacion.comentario if s.calificacion else None,
            "liberado_en": a_utc(s.liberado_en),
            "minutos_extension": s.minutos_extension,
            "falla_conexion_desde": a_utc(s.falla_conexion_desde),
        }
