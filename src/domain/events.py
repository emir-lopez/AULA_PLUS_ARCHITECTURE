"""Domain Events: hechos ya ocurridos, nombrados en pasado e inmutables.

Se registran solo DESPUÉS de una transición válida (validar -> cambiar estado ->
registrar evento) y la Unit of Work los guarda en el outbox en la misma
transacción que el Aggregate (ADR-002).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class EventoDominio:
    nombre: str
    agregado_id: str
    ocurrido_en: datetime
    datos: dict[str, Any] = field(default_factory=dict)


# Catálogo de nombres (lenguaje ubicuo). Sirve como documentación y evita typos.
SESION_RESERVADA = "SesionReservada"
PAGO_CONFIRMADO = "PagoConfirmado"
PAGO_RECHAZADO = "PagoRechazado"
SESION_CONFIRMADA = "SesionConfirmada"
CONGELAMIENTO_EXPIRADO = "CongelamientoExpirado"
SESION_CANCELADA = "SesionCancelada"
REEMBOLSO_CALCULADO = "ReembolsoCalculado"
SESION_COMPLETADA = "SesionCompletada"
SESION_ENVIADA_A_REVISION = "SesionEnviadaARevision"
NO_SHOW_REGISTRADO = "NoShowRegistrado"
DISPUTA_ABIERTA = "DisputaAbierta"
DISPUTA_RESUELTA = "DisputaResuelta"
FONDOS_LIBERADOS = "FondosLiberados"
SESION_CALIFICADA = "SesionCalificada"
SESION_EXTENDIDA = "SesionExtendida"
FALLA_CONEXION_REPORTADA = "FallaConexionReportada"
CONEXION_RESTABLECIDA = "ConexionRestablecida"
HORARIO_CONGELADO = "HorarioCongelado"
HORARIO_BLOQUEADO = "HorarioBloqueado"
HORARIO_LIBERADO = "HorarioLiberado"
MARCA_INCUMPLIMIENTO_REGISTRADA = "MarcaIncumplimientoRegistrada"
TUTOR_SUSPENDIDO = "TutorSuspendido"
