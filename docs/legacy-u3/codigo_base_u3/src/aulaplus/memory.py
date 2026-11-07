"""Infraestructura demostrativa en memoria; sustituible por persistencia relacional."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock

from .domain import (
    AgendaTutor, EstadoBloque, EventoDominio, ReglaDeNegocio,
    TransaccionSesion, VentanaHoraria,
)


@dataclass
class AlmacenMemoria:
    agendas: dict[str, AgendaTutor] = field(default_factory=dict)
    transacciones: dict[str, TransaccionSesion] = field(default_factory=dict)
    eventos_pendientes: list[EventoDominio] = field(default_factory=list)
    bloqueo: RLock = field(default_factory=RLock, repr=False)

    def unidad_de_trabajo(self) -> UnidadDeTrabajoMemoria:
        return UnidadDeTrabajoMemoria(self)


class _Transacciones:
    def __init__(self, datos: dict[str, TransaccionSesion]):
        self.datos = datos

    def obtener(self, sesion_id: str) -> TransaccionSesion:
        try:
            return self.datos[sesion_id]
        except KeyError as exc:
            raise ReglaDeNegocio("SesionNoEncontrada") from exc

    def agregar(self, sesion: TransaccionSesion) -> None:
        if sesion.sesion_id in self.datos:
            raise ReglaDeNegocio("SesionDuplicada")
        self.datos[sesion.sesion_id] = sesion

    def guardar(self, sesion: TransaccionSesion) -> None:
        if sesion.sesion_id not in self.datos:
            raise ReglaDeNegocio("SesionNoEncontrada")
        self.datos[sesion.sesion_id] = sesion


class _Agendas:
    def __init__(self, datos: dict[str, AgendaTutor]):
        self.datos = datos

    def obtener_del_tutor(self, tutor_id: str) -> AgendaTutor:
        try:
            return self.datos[tutor_id]
        except KeyError as exc:
            raise ReglaDeNegocio("TutorNoEncontrado") from exc

    def guardar(self, agenda: AgendaTutor) -> None:
        if agenda.tutor_id not in self.datos:
            raise ReglaDeNegocio("TutorNoEncontrado")
        self.datos[agenda.tutor_id] = agenda


class UnidadDeTrabajoMemoria:
    """Copia ambos Aggregates y confirma todo bajo un solo bloqueo.

    Es una implementación de práctica. Una base de datos requiere transacción,
    control de versiones por Aggregate y outbox persistente (ADR-002).
    """

    def __init__(self, almacen: AlmacenMemoria):
        self.almacen = almacen
        self._confirmada = False

    def __enter__(self) -> UnidadDeTrabajoMemoria:
        self.almacen.bloqueo.acquire()
        self._transacciones = deepcopy(self.almacen.transacciones)
        self._agendas = deepcopy(self.almacen.agendas)
        self.transacciones = _Transacciones(self._transacciones)
        self.agendas = _Agendas(self._agendas)
        return self

    def confirmar(self) -> None:
        eventos = []
        for raiz in (*self._transacciones.values(), *self._agendas.values()):
            eventos.extend(raiz.eventos)
            raiz.eventos.clear()
        self.almacen.transacciones = self._transacciones
        self.almacen.agendas = self._agendas
        self.almacen.eventos_pendientes.extend(eventos)
        self._confirmada = True

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        # Sin confirmar, los cambios solo existían en las copias de trabajo.
        self.almacen.bloqueo.release()


class RelojSistema:
    def ahora(self) -> datetime:
        return datetime.now(timezone.utc)


class RelojFijo:
    def __init__(self, momento: datetime):
        self.momento = momento

    def ahora(self) -> datetime:
        return self.momento


class LecturasMemoria:
    """Proyecta DTOs sin invocar comportamiento del modelo de escritura."""

    def __init__(self, almacen: AlmacenMemoria):
        self.almacen = almacen

    def detalle_sesion(self, sesion_id: str, usuario_id: str) -> dict[str, str]:
        with self.almacen.bloqueo:
            try:
                sesion = self.almacen.transacciones[sesion_id]
            except KeyError as exc:
                raise ReglaDeNegocio("SesionNoEncontrada") from exc
            if usuario_id not in (sesion.estudiante_id, sesion.tutor_id):
                raise ReglaDeNegocio("SinAccesoAlDetalle")
            return {
                "sesion_id": sesion.sesion_id,
                "estudiante_id": sesion.estudiante_id,
                "tutor_id": sesion.tutor_id,
                "estado": sesion.estado.value,
                "estado_pago": sesion.estado_pago.value,
                "monto": str(sesion.monto.monto),
            }

    def tutores_disponibles(self, ventana: VentanaHoraria, ahora: datetime) -> list[dict[str, str]]:
        filas: list[dict[str, str]] = []
        with self.almacen.bloqueo:
            for agenda in self.almacen.agendas.values():
                if ahora - agenda.actualizada_en > timedelta(days=7):
                    continue
                for bloque in agenda.bloques.values():
                    if (bloque.estado == EstadoBloque.DISPONIBLE
                            and bloque.ventana.inicio <= ventana.inicio
                            and bloque.ventana.fin >= ventana.fin):
                        filas.append({
                            "tutor_id": agenda.tutor_id, "bloque_id": bloque.bloque_id,
                            "inicio": bloque.ventana.inicio.isoformat(),
                            "fin": bloque.ventana.fin.isoformat(),
                        })
        return filas
