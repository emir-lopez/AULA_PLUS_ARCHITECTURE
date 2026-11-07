"""Integración contra PostgreSQL real (servicio "db" de docker compose / CI).

Se ejecutan solo si existe TEST_DATABASE_URL; en local sin Docker se omiten.
Verifican lo que SQLite no puede demostrar: tipos con zona horaria, bloqueo
FOR UPDATE de la sede y concurrencia real entre transacciones.
"""
import os
import threading
from datetime import timedelta

import pytest
from sqlalchemy import text

from api.container import construir_contenedor
from application.services import SolicitudReserva
from conftest import AHORA
from domain.exceptions import ConflictoDeRecurso, ReglaDeNegocioViolada
from domain.sede import Sede
from domain.value_objects import Dinero, Modalidad, VentanaHoraria
from infrastructure.config import Settings
from infrastructure.db import Base, crear_engine

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [pytest.mark.postgres, pytest.mark.skipif(not URL, reason="Requiere TEST_DATABASE_URL (PostgreSQL)")]


@pytest.fixture
def pg(reloj):
    engine = crear_engine(Settings(database_url=URL).url_normalizada)
    Base.metadata.drop_all(engine)
    engine.dispose()
    c = construir_contenedor(Settings(database_url=URL), reloj)
    c.agenda.registrar_tutor("T-1", "Tutor", Dinero("350"))
    inicio = AHORA + timedelta(days=1)
    c.agenda.agregar_bloque("T-1", "B-1", VentanaHoraria(inicio, inicio + timedelta(hours=1)))
    yield c


def test_es_postgres_y_conserva_zona_horaria(pg):
    with pg.consultas.lecturas.fabrica() as s:
        assert "PostgreSQL" in s.execute(text("select version()")).scalar()
    pg.reserva.reservar_sesion(SolicitudReserva("S-1", "E-1", "T-1", "B-1"))
    d = pg.consultas.lecturas.detalle_sesion("S-1")
    assert d["congelado_hasta"] == (AHORA + timedelta(minutes=10)).isoformat()
    assert d["monto"] == "350.00"


def test_reservas_concurrentes_del_mismo_bloque_solo_una_gana(pg):
    resultados: list[str] = []
    barrera = threading.Barrier(5)

    def intentar(i: int):
        barrera.wait()
        try:
            pg.reserva.reservar_sesion(SolicitudReserva(f"S-{i}", f"E-{i}", "T-1", "B-1"))
            resultados.append("ok")
        except (ReglaDeNegocioViolada, ConflictoDeRecurso) as exc:
            resultados.append(exc.codigo)

    hilos = [threading.Thread(target=intentar, args=(i,)) for i in range(5)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    assert resultados.count("ok") == 1, resultados


def test_ultimo_cupo_de_sede_entre_tutores_distintos(pg):
    """H-06: dos tutores distintos compiten por el último cupo; FOR UPDATE evita el sobrecupo."""
    pg.agenda.registrar_sede(Sede("SEDE-1", "Sala", cupo_maximo=1))
    inicio = AHORA + timedelta(days=1)
    for t in ("T-2", "T-3", "T-4"):
        pg.agenda.registrar_tutor(t, t, Dinero("100"))
        pg.agenda.agregar_bloque(t, "B-1", VentanaHoraria(inicio, inicio + timedelta(hours=1)))
    resultados: list[str] = []
    barrera = threading.Barrier(3)

    def intentar(tutor: str):
        barrera.wait()
        try:
            pg.reserva.reservar_sesion(SolicitudReserva(f"S-{tutor}", "E", tutor, "B-1", Modalidad.PRESENCIAL,
                                                        "SEDE-1"))
            resultados.append("ok")
        except (ReglaDeNegocioViolada, ConflictoDeRecurso) as exc:
            resultados.append(exc.codigo)

    hilos = [threading.Thread(target=intentar, args=(t,)) for t in ("T-2", "T-3", "T-4")]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    assert resultados.count("ok") == 1 and resultados.count("SinCupoEnSede") == 2, resultados
