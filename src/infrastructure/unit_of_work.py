"""Unit of Work SQLAlchemy: una transacción local por caso de uso (ADR-002).

* ``confirmar`` extrae los Domain Events de los Aggregates tocados, los escribe en
  el outbox y hace COMMIT: Aggregates + eventos se guardan juntos o no se guardan.
* Si el bloque ``with`` termina sin confirmar o con excepción, se hace ROLLBACK.
"""
from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from .db import EventoOutboxRow, a_utc
from .repositories import (
    Rastreador,
    RepositorioSqlAgendaTutor,
    RepositorioSqlSede,
    RepositorioSqlTransaccionSesion,
)


class UnidadDeTrabajoSql:
    def __init__(self, fabrica_sesiones: sessionmaker):
        self._fabrica = fabrica_sesiones
        self.session: Session | None = None
        self._confirmada = False

    def __enter__(self) -> UnidadDeTrabajoSql:
        self.session = self._fabrica()
        self._rastreador = Rastreador()
        self.transacciones = RepositorioSqlTransaccionSesion(self.session, self._rastreador)
        self.agendas = RepositorioSqlAgendaTutor(self.session, self._rastreador)
        self.sedes = RepositorioSqlSede(self.session)
        self._confirmada = False
        return self

    def confirmar(self) -> None:
        assert self.session is not None
        for agregado in self._rastreador.vistos:
            for evento in agregado.extraer_eventos():
                self.session.add(EventoOutboxRow(nombre=evento.nombre, agregado_id=evento.agregado_id,
                                                 ocurrido_en=a_utc(evento.ocurrido_en),
                                                 datos=_serializable(evento.datos)))
        self.session.commit()
        self._confirmada = True

    def revertir(self) -> None:
        if self.session is not None:
            self.session.rollback()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if not self._confirmada:
            self.revertir()
        if self.session is not None:
            self.session.close()


def _serializable(datos: dict) -> dict:
    return {k: (v if isinstance(v, str | int | float | bool) or v is None else str(v)) for k, v in datos.items()}


class FabricaUnidadDeTrabajoSql:
    def __init__(self, fabrica_sesiones: sessionmaker):
        self.fabrica_sesiones = fabrica_sesiones

    def __call__(self) -> UnidadDeTrabajoSql:
        return UnidadDeTrabajoSql(self.fabrica_sesiones)
