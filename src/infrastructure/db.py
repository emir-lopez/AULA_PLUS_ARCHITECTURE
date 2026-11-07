"""Modelo relacional (SQLAlchemy 2). Filas separadas de las entidades del dominio.

Montos en centavos enteros (sin pérdida de precisión) y fechas en UTC.
Funciona con PostgreSQL (Docker / producción) y SQLite (desarrollo y pruebas).
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class AgendaRow(Base):
    __tablename__ = "agendas"
    tutor_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tarifa_hora: Mapped[str] = mapped_column(String(20))
    actualizada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    marcas_incumplimiento: Mapped[int] = mapped_column(Integer, default=0)
    suspendido: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=0)


class BloqueRow(Base):
    __tablename__ = "bloques"
    bloque_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tutor_id: Mapped[str] = mapped_column(ForeignKey("agendas.tutor_id"), primary_key=True)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(String(20))
    sesion_id: Mapped[str | None] = mapped_column(String(40), nullable=True)


class SedeRow(Base):
    __tablename__ = "sedes"
    sede_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    cupo_maximo: Mapped[int] = mapped_column(Integer)
    radio_geocerca_m: Mapped[int] = mapped_column(Integer, default=200)


class SesionRow(Base):
    __tablename__ = "sesiones"
    sesion_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    estudiante_id: Mapped[str] = mapped_column(String(40), index=True)
    tutor_id: Mapped[str] = mapped_column(String(40), index=True)
    bloque_id: Mapped[str] = mapped_column(String(40))
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    modalidad: Mapped[str] = mapped_column(String(20))
    sede_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    monto_centavos: Mapped[int] = mapped_column(Integer)
    congelado_hasta: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(String(20), index=True)
    estado_pago: Mapped[str] = mapped_column(String(20))
    intentos_pago_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    comision_centavos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    neto_centavos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    porcentaje_comision: Mapped[str | None] = mapped_column(String(10), nullable=True)
    completada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reembolso_centavos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    motivo_revision: Mapped[str | None] = mapped_column(String(60), nullable=True)
    parte_ausente: Mapped[str | None] = mapped_column(String(20), nullable=True)
    disputa_motivo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    disputa_abierta_por: Mapped[str | None] = mapped_column(String(40), nullable=True)
    disputa_abierta_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disputa_limite: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disputa_resolucion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    disputa_resuelta_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    calificacion_puntos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calificacion_comentario: Mapped[str | None] = mapped_column(String(500), nullable=True)
    liberado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)


class EventoOutboxRow(Base):
    """Outbox transaccional (ADR-002): el evento se guarda junto con el Aggregate."""

    __tablename__ = "eventos_outbox"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(60))
    agregado_id: Mapped[str] = mapped_column(String(40), index=True)
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    datos: Mapped[dict] = mapped_column(JSON, default=dict)
    publicado: Mapped[bool] = mapped_column(Boolean, default=False)


def a_utc(valor: datetime | None) -> datetime | None:
    """SQLite no guarda zona horaria: se normaliza a UTC al leer y al escribir."""
    if valor is None:
        return None
    if valor.tzinfo is None:
        return valor.replace(tzinfo=UTC)
    return valor.astimezone(UTC)


def crear_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True)


def crear_esquema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def crear_fabrica_sesiones(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
