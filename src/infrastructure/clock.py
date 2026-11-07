"""Relojes: el dominio nunca llama a datetime.now(); recibe la hora de un puerto Reloj."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import UTC, datetime

_fecha_simulada: ContextVar[datetime | None] = ContextVar("fecha_simulada", default=None)


class RelojSistema:
    """Hora real UTC. En demo puede sobrescribirse por petición (cabecera X-Fecha-Simulada)."""

    def ahora(self) -> datetime:
        simulada = _fecha_simulada.get()
        return simulada if simulada is not None else datetime.now(UTC)

    @staticmethod
    def simular(valor: datetime | None):
        return _fecha_simulada.set(valor)

    @staticmethod
    def restaurar(token) -> None:
        _fecha_simulada.reset(token)


class RelojFijo:
    """Para pruebas: la hora solo avanza cuando la prueba lo indica."""

    def __init__(self, momento: datetime):
        self.momento = momento

    def ahora(self) -> datetime:
        return self.momento
