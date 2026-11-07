"""Fixtures compartidas. Reloj fijo para que los plazos (2 h, 10 min, 48 h, 72 h) sean reproducibles."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from api.container import construir_contenedor
from domain.agenda import AgendaTutor
from domain.policies import ParametrosOperacion
from domain.sesion import TransaccionSesion
from domain.specifications import SolicitudDeReserva
from domain.value_objects import Dinero, Modalidad, VentanaHoraria
from infrastructure.clock import RelojFijo
from infrastructure.config import Settings

AHORA = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
PAQUETE = Path(__file__).parent / "data" / "paquete_pia"


@pytest.fixture
def ahora() -> datetime:
    return AHORA


@pytest.fixture
def params() -> ParametrosOperacion:
    return ParametrosOperacion()


@pytest.fixture
def ventana() -> VentanaHoraria:
    inicio = AHORA + timedelta(days=1)
    return VentanaHoraria(inicio, inicio + timedelta(hours=1))


def nueva_sesion(ventana: VentanaHoraria, ahora: datetime = AHORA, monto: str = "350.00",
                 modalidad: Modalidad = Modalidad.EN_LINEA, sede_id: str | None = None) -> TransaccionSesion:
    solicitud = SolicitudDeReserva(ventana.inicio, ahora, ahora, False, True, modalidad == Modalidad.PRESENCIAL,
                                   0, 5)
    return TransaccionSesion.reservar(
        sesion_id="S-1", estudiante_id="E-1", tutor_id="T-1", bloque_id="B-1", ventana=ventana,
        modalidad=modalidad, monto=Dinero(Decimal(monto)), solicitud=solicitud, params=ParametrosOperacion(),
        sede_id=sede_id,
    )


@pytest.fixture
def sesion(ventana) -> TransaccionSesion:
    return nueva_sesion(ventana)


@pytest.fixture
def agenda(ventana) -> AgendaTutor:
    a = AgendaTutor("T-1", "Tutor Uno", "350.00", AHORA)
    a.agregar_bloque("B-1", ventana, AHORA)
    return a


@pytest.fixture
def reloj() -> RelojFijo:
    return RelojFijo(AHORA)


@pytest.fixture
def contenedor(reloj):
    """Contenedor real (servicios + SQLAlchemy) sobre SQLite en memoria."""
    return construir_contenedor(Settings(database_url="sqlite://", seed_demo=False), reloj)


@pytest.fixture
def con_tutor(contenedor):
    c = contenedor
    c.agenda.registrar_tutor("T-1", "Tutor Uno", Dinero("350.00"))
    inicio = AHORA + timedelta(days=1)
    c.agenda.agregar_bloque("T-1", "B-1", VentanaHoraria(inicio, inicio + timedelta(hours=1)))
    c.agenda.agregar_bloque("T-1", "B-2", VentanaHoraria(inicio + timedelta(hours=2), inicio + timedelta(hours=4)))
    return c
