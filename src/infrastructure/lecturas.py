"""Lado de lectura CQRS: consultas directas sobre las tablas, devuelven DTOs (dict), no Aggregates."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from domain.events import EventoDominio
from domain.state_machine import EstadoBloque, EstadoPago, EstadoSesion
from domain.value_objects import VentanaHoraria

from .db import AgendaRow, BloqueRow, EventoOutboxRow, SesionRow, a_utc


def _iso(valor: datetime | None) -> str | None:
    valor = a_utc(valor)
    return valor.isoformat() if valor else None


def _pesos(centavos: int | None) -> str | None:
    return None if centavos is None else f"{centavos / 100:.2f}"


class LecturasSql:
    def __init__(self, fabrica_sesiones: sessionmaker):
        self.fabrica = fabrica_sesiones

    def detalle_sesion(self, sesion_id: str) -> dict:
        with self.fabrica() as s:
            f = s.get(SesionRow, sesion_id)
            if f is None:
                return {}
            return {
                "sesion_id": f.sesion_id, "estudiante_id": f.estudiante_id, "tutor_id": f.tutor_id,
                "bloque_id": f.bloque_id, "modalidad": f.modalidad, "sede_id": f.sede_id,
                "inicio": _iso(f.inicio), "fin": _iso(f.fin), "estado": f.estado, "estado_pago": f.estado_pago,
                "monto": _pesos(f.monto_centavos), "congelado_hasta": _iso(f.congelado_hasta),
                "intentos_pago_fallidos": f.intentos_pago_fallidos,
                "comision": _pesos(f.comision_centavos), "neto_tutor": _pesos(f.neto_centavos),
                "completada_en": _iso(f.completada_en), "reembolso": _pesos(f.reembolso_centavos),
                "motivo_revision": f.motivo_revision, "parte_ausente": f.parte_ausente,
                "disputa": None if f.disputa_motivo is None else {
                    "motivo": f.disputa_motivo, "abierta_por": f.disputa_abierta_por,
                    "abierta_en": _iso(f.disputa_abierta_en), "fecha_limite": _iso(f.disputa_limite),
                    "resolucion": f.disputa_resolucion, "resuelta_en": _iso(f.disputa_resuelta_en),
                },
                "calificacion": f.calificacion_puntos, "liberado_en": _iso(f.liberado_en),
                "minutos_extension": f.minutos_extension or 0, "falla_conexion_desde": _iso(f.falla_conexion_desde),
                "version": f.version,
            }

    def tutores_disponibles(self, ventana: VentanaHoraria, ahora: datetime, dias_vigencia: int) -> list[dict]:
        limite = a_utc(ahora) - timedelta(days=dias_vigencia)
        with self.fabrica() as s:
            filas = s.execute(
                select(AgendaRow, BloqueRow)
                .join(BloqueRow, BloqueRow.tutor_id == AgendaRow.tutor_id)
                .where(AgendaRow.suspendido.is_(False), BloqueRow.estado == EstadoBloque.DISPONIBLE.value)
                .order_by(AgendaRow.tutor_id, BloqueRow.inicio)
            ).all()
        resultado = []
        for agenda, bloque in filas:
            if a_utc(agenda.actualizada_en) < limite:
                continue  # US-11: perfil oculto
            if a_utc(bloque.inicio) <= ventana.inicio and a_utc(bloque.fin) >= ventana.fin:
                resultado.append({"tutor_id": agenda.tutor_id, "nombre": agenda.nombre,
                                  "tarifa_hora": agenda.tarifa_hora, "bloque_id": bloque.bloque_id,
                                  "inicio": _iso(bloque.inicio), "fin": _iso(bloque.fin)})
        return resultado

    def pagos_listos_para_liberar(self, ahora: datetime, horas_retencion: int) -> list[str]:
        limite = a_utc(ahora) - timedelta(hours=horas_retencion)
        with self.fabrica() as s:
            filas = s.execute(
                select(SesionRow.sesion_id, SesionRow.completada_en, SesionRow.disputa_resuelta_en,
                       SesionRow.disputa_motivo)
                .where(SesionRow.estado == EstadoSesion.COMPLETADA.value,
                       SesionRow.estado_pago == EstadoPago.CONFIRMADO.value)
            ).all()
        return [
            sid for sid, completada, resuelta, motivo in filas
            if completada and a_utc(completada) <= limite and (motivo is None or resuelta is not None)
        ]

    def disputas_pendientes(self) -> list[dict]:
        with self.fabrica() as s:
            filas = s.scalars(
                select(SesionRow).where(SesionRow.estado == EstadoSesion.EN_REVISION.value)
                .order_by(SesionRow.disputa_limite)
            ).all()
            return [{"sesion_id": f.sesion_id, "motivo": f.disputa_motivo or f.motivo_revision,
                     "abierta_por": f.disputa_abierta_por, "fecha_limite": _iso(f.disputa_limite)}
                    for f in filas]

    def eventos(self, agregado_id: str | None = None) -> list[EventoDominio]:
        with self.fabrica() as s:
            consulta = select(EventoOutboxRow).order_by(EventoOutboxRow.id)
            if agregado_id:
                consulta = consulta.where(EventoOutboxRow.agregado_id == agregado_id)
            return [EventoDominio(e.nombre, e.agregado_id, a_utc(e.ocurrido_en), e.datos or {})
                    for e in s.scalars(consulta).all()]

    def indicadores(self) -> dict:
        """KPIs del BRD (sección 9)."""
        with self.fabrica() as s:
            por_estado = dict(s.execute(select(SesionRow.estado, func.count()).group_by(SesionRow.estado)).all())
            comisiones = s.scalar(select(func.coalesce(func.sum(SesionRow.comision_centavos), 0)).where(
                SesionRow.estado_pago == EstadoPago.LIBERADO.value)) or 0
            reembolsos = s.scalar(select(func.coalesce(func.sum(SesionRow.reembolso_centavos), 0))) or 0
            transaccionado = s.scalar(select(func.coalesce(func.sum(SesionRow.monto_centavos), 0)).where(
                SesionRow.estado_pago != EstadoPago.PENDIENTE.value)) or 0
            disputadas = s.scalar(select(func.count()).select_from(SesionRow).where(
                SesionRow.disputa_motivo.is_not(None))) or 0
        completadas = por_estado.get(EstadoSesion.COMPLETADA.value, 0)
        canceladas = por_estado.get(EstadoSesion.CANCELADA.value, 0) + por_estado.get(EstadoSesion.NO_SHOW.value, 0)
        cerradas = completadas + canceladas + por_estado.get(EstadoSesion.EN_REVISION.value, 0)
        return {
            "sesiones_por_estado": por_estado,
            "tasa_completadas": round(completadas / cerradas, 4) if cerradas else None,
            "sesiones_disputadas": disputadas,
            "ingreso_comisiones": _pesos(comisiones),
            "total_reembolsado": _pesos(reembolsos),
            "porcentaje_reembolsos": round(reembolsos / transaccionado, 4) if transaccionado else None,
        }
