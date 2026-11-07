"""Contratos de aplicación: escritura, transacción, reloj y lectura CQRS."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .domain import AgendaTutor, TransaccionSesion, VentanaHoraria


class RepositorioTransaccionSesion(Protocol):
    def obtener(self, sesion_id: str) -> TransaccionSesion: ...
    def agregar(self, sesion: TransaccionSesion) -> None: ...
    def guardar(self, sesion: TransaccionSesion) -> None: ...


class RepositorioAgendaTutor(Protocol):
    def obtener_del_tutor(self, tutor_id: str) -> AgendaTutor: ...
    def guardar(self, agenda: AgendaTutor) -> None: ...


class UnidadDeTrabajo(Protocol):
    transacciones: RepositorioTransaccionSesion
    agendas: RepositorioAgendaTutor

    def __enter__(self) -> UnidadDeTrabajo: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...
    def confirmar(self) -> None: ...


class Reloj(Protocol):
    def ahora(self) -> datetime: ...


class LecturasAulaPlus(Protocol):
    """Devuelve DTOs de lectura, sin exponer Aggregates de escritura."""

    def detalle_sesion(self, sesion_id: str, usuario_id: str) -> dict[str, str]: ...
    def tutores_disponibles(self, ventana: VentanaHoraria, ahora: datetime) -> list[dict[str, str]]: ...

