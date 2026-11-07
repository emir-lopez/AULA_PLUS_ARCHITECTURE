"""Carga demo idempotente con horarios futuros y cabecera X-Fecha-Simulada visible en Swagger/OpenAPI."""
from datetime import timedelta

from fastapi.testclient import TestClient

from api.container import construir_contenedor
from api.main import create_app
from application.queries import ObtenerTutoresDisponiblesQuery
from conftest import AHORA
from domain.value_objects import Dinero, VentanaHoraria
from infrastructure.config import Settings
from infrastructure.seed import bloques_demo, sembrar


def _bloques(c, tutor="T-001"):
    with c.agenda.fabrica_uow() as uow:
        return uow.agendas.obtener_del_tutor(tutor).bloques


def test_seed_crea_14_dias_y_es_idempotente(contenedor):
    assert sembrar(contenedor.agenda, AHORA) == 3 * 14 * 4
    assert sembrar(contenedor.agenda, AHORA) == 0  # segunda ejecución: no duplica
    assert len(_bloques(contenedor)) == 14 * 4


def test_seed_completa_dias_nuevos_y_mantiene_perfiles_visibles(contenedor, reloj):
    sembrar(contenedor.agenda, AHORA)
    reloj.momento = AHORA + timedelta(days=20)  # más de 7 días después (R-10)
    assert sembrar(contenedor.agenda, reloj.momento) == 3 * 14 * 4  # todos los días son nuevos
    dia = (reloj.momento + timedelta(days=3)).replace(hour=16, minute=0, second=0, microsecond=0)
    ventana = VentanaHoraria(dia, dia + timedelta(hours=1))
    disponibles = contenedor.consultas.tutores_disponibles(ObtenerTutoresDisponiblesQuery(ventana))
    assert {t["tutor_id"] for t in disponibles} == {"T-001", "T-002", "T-003"}


def test_publicar_disponibilidad_omite_empalmes(contenedor):
    contenedor.agenda.registrar_tutor("T-9", "Tutor", Dinero("100"))
    bloques = bloques_demo(AHORA, 1)
    inicio = bloques[0][1].inicio
    empalmado = ("B-EMPALME", VentanaHoraria(inicio + timedelta(minutes=30), inicio + timedelta(minutes=90)))
    assert contenedor.agenda.publicar_disponibilidad("T-9", bloques + [empalmado]) == 4


def test_swagger_muestra_la_cabecera_de_fecha_simulada(reloj):
    settings = Settings(database_url="sqlite://", permitir_fecha_simulada=True)
    with TestClient(create_app(settings, construir_contenedor(settings, reloj))) as c:
        esquema = c.get("/openapi.json").json()
        for ruta, metodo in [("/sesiones/{sesion_id}/completar", "post"), ("/sesiones/{sesion_id}/liberacion", "post"),
                             ("/sesiones", "post"), ("/indicadores", "get")]:
            params = esquema["paths"][ruta][metodo].get("parameters", [])
            assert any(p["name"] == "X-Fecha-Simulada" and p["in"] == "header" and not p.get("required")
                       for p in params), ruta
