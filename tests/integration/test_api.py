"""Pruebas de la API REST (contrato HTTP): 200/201, 400, 404, 409 y 422."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from conftest import AHORA
from infrastructure.config import Settings

INICIO = AHORA + timedelta(days=1)
FIN = INICIO + timedelta(hours=1)


def h(momento):
    return {"X-Fecha-Simulada": momento.isoformat()}


@pytest.fixture
def client():
    # Reloj del sistema + cabecera X-Fecha-Simulada: así se prueba también el middleware de la demo.
    from api.container import construir_contenedor
    settings = Settings(database_url="sqlite://", permitir_fecha_simulada=True, seed_demo=False)
    app = create_app(settings, construir_contenedor(settings))
    with TestClient(app, headers=h(AHORA)) as c:
        c.post("/tutores", json={"tutor_id": "T-1", "nombre": "Tutor Uno", "tarifa_hora": "350.00"})
        c.post("/tutores/T-1/bloques", json={"bloque_id": "B-1", "inicio": INICIO.isoformat(),
                                             "fin": FIN.isoformat()})
        yield c


def reservar(client, sesion_id="S-1"):
    return client.post("/sesiones", json={"sesion_id": sesion_id, "estudiante_id": "E-1",
                                          "tutor_id": "T-1", "bloque_id": "B-1"})


def pagar(client, monto="350.00", **extra):
    return client.post("/sesiones/S-1/pago", json={"monto": monto, **extra})


EVIDENCIA = {"conexion_tutor": FIN.isoformat(), "conexion_estudiante": FIN.isoformat(),
             "confirma_estudiante": True, "confirma_tutor": True}


def test_health_y_docs(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/docs").status_code == 200
    esquema = client.get("/openapi.json").json()
    assert "/sesiones/{sesion_id}/liberacion" in esquema["paths"]
    assert client.get("/", follow_redirects=False).status_code == 307


def test_201_reserva_y_200_pago(client):
    r = reservar(client)
    assert r.status_code == 201 and r.json()["estado"] == "Reservada" and r.json()["monto"] == "350.00"
    r = pagar(client)
    assert r.status_code == 200 and r.json()["estado"] == "Confirmada"


def test_422_regla_de_negocio(client):
    reservar(client)
    r = pagar(client, "100.00")
    assert r.status_code == 422 and r.json()["codigo"] == "MontoDePagoIncorrecto"


def test_409_transicion_invalida_doble_pago(client):
    reservar(client)
    pagar(client)
    r = pagar(client)
    assert r.status_code == 409 and r.json()["codigo"] == "TransicionInvalida"


def test_bloque_ocupado_422_y_sesion_duplicada_409(client):
    reservar(client)
    r = reservar(client, "S-2")
    assert r.status_code == 422 and r.json()["codigo"] == "HorarioNoDisponible"
    client.post("/tutores/T-1/bloques", json={"bloque_id": "B-2", "inicio": (FIN + timedelta(hours=1)).isoformat(),
                                              "fin": (FIN + timedelta(hours=2)).isoformat()})
    r = client.post("/sesiones", json={"sesion_id": "S-1", "estudiante_id": "E-1", "tutor_id": "T-1",
                                       "bloque_id": "B-2"})
    assert r.status_code == 409 and r.json()["codigo"] == "SesionDuplicada"
    r = client.post("/tutores", json={"tutor_id": "T-1", "nombre": "x", "tarifa_hora": "1"})
    assert r.status_code == 409


def test_404_inexistentes(client):
    assert client.get("/sesiones/NO").status_code == 404
    assert client.get("/sesiones/NO/eventos").status_code == 404
    assert client.post("/sesiones/NO/liberacion").json()["codigo"] == "SesionNoEncontrada"
    r = client.post("/sesiones", json={"sesion_id": "X", "estudiante_id": "E", "tutor_id": "NO", "bloque_id": "B"})
    assert r.status_code == 404


def test_400_dato_invalido(client):
    r = client.post("/tutores/T-1/bloques", json={"bloque_id": "B-X", "inicio": FIN.isoformat(),
                                                  "fin": INICIO.isoformat()})
    assert r.status_code == 400 and r.json()["codigo"] == "VentanaInvalida"
    assert client.get("/health", headers={"X-Fecha-Simulada": "ayer"}).status_code == 400


def test_422_validacion_de_esquema(client):
    assert client.post("/tutores", json={"tutor_id": "", "nombre": "x", "tarifa_hora": -1}).status_code == 422


def test_pago_fallido_y_expiracion(client):
    reservar(client)
    r = pagar(client, resultado="Fallido", motivo="Tarjeta rechazada")
    assert r.json()["intentos_pago_fallidos"] == 1
    r = client.post("/sesiones/S-1/expirar", headers=h(AHORA + timedelta(minutes=11)))
    assert r.json()["expirada"] is True and r.json()["estado"] == "Cancelada"


def test_flujo_completo_con_fecha_simulada(client):
    reservar(client)
    pagar(client)
    r = client.post("/sesiones/S-1/completar", json=EVIDENCIA, headers=h(FIN))
    assert r.json()["estado"] == "Completada" and r.json()["comision"] == "70.00"
    r = client.post("/sesiones/S-1/calificacion", json={"estudiante_id": "E-1", "puntos": 5}, headers=h(FIN))
    assert r.json()["calificacion"] == 5
    assert client.post("/sesiones/S-1/liberacion", headers=h(FIN + timedelta(hours=1))).status_code == 422
    assert client.get("/liquidaciones/pendientes", headers=h(FIN + timedelta(hours=48))).json() == ["S-1"]
    r = client.post("/sesiones/S-1/liberacion", headers=h(FIN + timedelta(hours=48)))
    assert r.status_code == 200 and r.json()["estado_pago"] == "Liberado" and r.json()["neto_tutor"] == "280.00"
    eventos = [e["nombre"] for e in client.get("/sesiones/S-1/eventos").json()]
    assert eventos[-1] == "FondosLiberados"
    assert client.get("/indicadores").json()["ingreso_comisiones"] == "70.00"


def test_disputa_y_resolucion(client):
    reservar(client)
    pagar(client)
    client.post("/sesiones/S-1/completar", json=EVIDENCIA, headers=h(FIN))
    r = client.post("/sesiones/S-1/disputa", json={"solicitante_id": "E-1", "motivo": "Duró menos"}, headers=h(FIN))
    assert r.json()["estado"] == "EnRevision" and r.json()["disputa"]["fecha_limite"]
    assert client.get("/soporte/disputas").json()[0]["sesion_id"] == "S-1"
    r = client.post("/sesiones/S-1/resolucion", json={"a_favor_de": "Estudiante", "resolucion": "Reembolso total"},
                    headers=h(FIN + timedelta(hours=5)))
    assert r.json()["estado"] == "Cancelada" and r.json()["reembolso"] == "350.00"


def test_cancelaciones_y_no_show(client):
    reservar(client)
    pagar(client)
    r = client.post("/sesiones/S-1/cancelacion-estudiante", json={"solicitante_id": "E-1"},
                    headers=h(INICIO - timedelta(hours=30)))
    assert r.json()["reembolso"] == "350.00"
    client.post("/tutores/T-1/bloques", json={"bloque_id": "B-2", "inicio": (INICIO + timedelta(hours=3)).isoformat(),
                                              "fin": (INICIO + timedelta(hours=4)).isoformat()})
    client.post("/sesiones", json={"sesion_id": "S-2", "estudiante_id": "E-2", "tutor_id": "T-1", "bloque_id": "B-2"})
    client.post("/sesiones/S-2/pago", json={"monto": "350.00"})
    r = client.post("/sesiones/S-2/no-show", json={"parte_ausente": "Tutor"},
                    headers=h(INICIO + timedelta(hours=3, minutes=10)))
    assert r.json()["estado"] == "NoShow" and r.json()["reembolso"] == "350.00"
    client.post("/tutores/T-1/bloques", json={"bloque_id": "B-3", "inicio": (INICIO + timedelta(hours=6)).isoformat(),
                                              "fin": (INICIO + timedelta(hours=7)).isoformat()})
    client.post("/sesiones", json={"sesion_id": "S-3", "estudiante_id": "E-3", "tutor_id": "T-1", "bloque_id": "B-3"})
    client.post("/sesiones/S-3/pago", json={"monto": "350.00"})
    r = client.post("/sesiones/S-3/cancelacion-tutor", json={"solicitante_id": "T-1"})
    assert r.json()["estado"] == "Cancelada" and r.json()["estado_pago"] == "Reembolsado"


def test_consultas_de_disponibilidad_y_sede(client):
    disponibles = client.get("/tutores/disponibles", params={"inicio": INICIO.isoformat(), "fin": FIN.isoformat()})
    assert [t["bloque_id"] for t in disponibles.json()] == ["B-1"]
    r = client.post("/sedes", json={"sede_id": "SEDE-1", "nombre": "Sala", "cupo_maximo": 3})
    assert r.status_code == 201
    assert client.post("/sedes", json={"sede_id": "SEDE-1", "nombre": "Sala", "cupo_maximo": 3}).status_code == 409


def test_seed_demo_y_fecha_simulada_deshabilitada(reloj):
    from api.container import construir_contenedor
    settings = Settings(database_url="sqlite://", seed_demo=True, permitir_fecha_simulada=False)
    with TestClient(create_app(settings, construir_contenedor(settings, reloj))) as c:
        r = c.get("/tutores/disponibles", params={"inicio": "2026-11-11T16:00:00+00:00",
                                                  "fin": "2026-11-11T17:00:00+00:00"})
        assert len(r.json()) == 3
        # Sin PERMITIR_FECHA_SIMULADA la cabecera se ignora.
        assert c.get("/health", headers={"X-Fecha-Simulada": "x"}).status_code == 200


def test_consultas_de_la_interfaz_web(client):
    client.post("/sedes", json={"sede_id": "SEDE-1", "nombre": "Biblioteca", "cupo_maximo": 2})
    reservar(client)
    assert client.get("/sesiones").json() == [{
        "sesion_id": "S-1", "estudiante_id": "E-1", "tutor_id": "T-1", "modalidad": "EnLinea",
        "inicio": INICIO.isoformat(), "fin": FIN.isoformat(), "estado": "Reservada",
        "estado_pago": "Pendiente", "monto": "350.00"}]
    tutor = client.get("/tutores").json()[0]
    assert (tutor["tutor_id"], tutor["suspendido"], tutor["marcas_incumplimiento"]) == ("T-1", False, 0)
    assert tutor["bloques"] == [{"bloque_id": "B-1", "inicio": INICIO.isoformat(), "fin": FIN.isoformat(),
                                 "estado": "Congelado", "sesion_id": "S-1"}]
    # Los bloques que ya terminaron no se muestran en la agenda.
    assert client.get("/tutores", headers=h(FIN + timedelta(minutes=1))).json()[0]["bloques"] == []
    assert client.get("/sedes").json() == [{"sede_id": "SEDE-1", "nombre": "Biblioteca", "cupo_maximo": 2}]
    parametros = client.get("/parametros").json()
    assert parametros["ahora"] == AHORA.isoformat() and parametros["permitir_fecha_simulada"] is True
    assert (parametros["minutos_congelamiento"], parametros["horas_retencion"],
            parametros["marcas_para_suspension"]) == (10, 48, 3)


def test_interfaz_web_se_sirve_en_app(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/app/"
    pagina = client.get("/app/")
    assert pagina.status_code == 200 and "AulaPlus" in pagina.text
    assert client.get("/app/app.js").status_code == 200
    assert client.get("/app/styles.css").status_code == 200
