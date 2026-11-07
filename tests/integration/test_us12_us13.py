"""US-12 (extensión de sesión) y US-13 (falla de conexión): dominio, servicio con agenda, API y migración."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from api.container import construir_contenedor
from api.main import create_app
from application.services import SolicitudReserva
from conftest import AHORA, nueva_sesion
from domain.exceptions import ConflictoDeRecurso, DatoInvalido, ReglaDeNegocioViolada, TransicionInvalida
from domain.policies import ParametrosOperacion
from domain.state_machine import EstadoSesion
from domain.value_objects import Dinero, Modalidad, VentanaHoraria
from infrastructure.config import Settings
from infrastructure.db import crear_esquema

PARAMS = ParametrosOperacion()
TARIFA = Dinero("350.00")


def en_curso(ventana, **kw):
    s = nueva_sesion(ventana, **kw)
    s.confirmar_pago(s.monto, AHORA)
    return s, ventana.inicio + timedelta(minutes=30)


class TestExtensionDominio:
    def test_us12_extiende_y_cobra_en_plataforma(self, ventana):
        s, durante = en_curso(ventana)
        costo = s.extender("E-1", 30, TARIFA, Dinero("175.00"), durante)
        assert costo == Dinero("175.00") and s.monto == Dinero("525.00")
        assert s.ventana.fin == ventana.fin + timedelta(minutes=30) and s.minutos_extension == 30
        assert s.eventos[-1].nombre == "SesionExtendida"

    @pytest.mark.parametrize("minutos, monto, error", [
        (20, "116.67", "ExtensionInvalida"),
        (75, "437.50", "ExtensionExcedeMaximo"),
        (30, "100.00", "MontoDeExtensionIncorrecto"),
    ])
    def test_validaciones(self, ventana, minutos, monto, error):
        s, durante = en_curso(ventana)
        with pytest.raises((DatoInvalido, ReglaDeNegocioViolada), match=error):
            s.extender("E-1", minutos, TARIFA, Dinero(monto), durante)
        assert s.minutos_extension == 0 and s.ventana == ventana

    def test_maximo_acumulado_60_minutos(self, ventana):
        s, durante = en_curso(ventana)
        s.extender("E-1", 45, TARIFA, Dinero("262.50"), durante)
        with pytest.raises(ReglaDeNegocioViolada, match="ExtensionExcedeMaximo"):
            s.extender("E-1", 30, TARIFA, Dinero("175.00"), durante)

    def test_solo_en_curso_y_solo_el_estudiante(self, ventana):
        s, durante = en_curso(ventana)
        with pytest.raises(ReglaDeNegocioViolada, match="SolicitanteNoEsElEstudiante"):
            s.extender("T-1", 15, TARIFA, Dinero("87.50"), durante)
        with pytest.raises(ReglaDeNegocioViolada, match="SesionNoEnCurso"):
            s.extender("E-1", 15, TARIFA, Dinero("87.50"), ventana.inicio - timedelta(minutes=1))
        with pytest.raises(ReglaDeNegocioViolada, match="SesionNoEnCurso"):
            nueva_sesion(ventana).extender("E-1", 15, TARIFA, Dinero("87.50"), durante)


class TestFallaConexionDominio:
    def test_reconexion_dentro_de_15_min_continua(self, ventana):
        s, durante = en_curso(ventana)
        s.reportar_falla_conexion("T-1", durante)
        assert s.falla_conexion_desde == durante
        assert s.registrar_reconexion(durante + timedelta(minutes=15), PARAMS) == EstadoSesion.CONFIRMADA
        assert [e.nombre for e in s.eventos][-2:] == ["FallaConexionReportada", "ConexionRestablecida"]
        assert s.falla_conexion_desde is None

    def test_mas_de_15_min_pasa_a_revision(self, ventana):
        s, durante = en_curso(ventana)
        s.reportar_falla_conexion("E-1", durante)
        assert s.registrar_reconexion(durante + timedelta(minutes=15, seconds=1), PARAMS) == EstadoSesion.EN_REVISION
        assert s.motivo_revision == "FallaDeConexion"

    def test_validaciones(self, ventana):
        s, durante = en_curso(ventana)
        with pytest.raises(ReglaDeNegocioViolada, match="SinFallaReportada"):
            s.registrar_reconexion(durante, PARAMS)
        with pytest.raises(ReglaDeNegocioViolada, match="SolicitanteNoEsParteDeLaSesion"):
            s.reportar_falla_conexion("X", durante)
        s.reportar_falla_conexion("E-1", durante)
        with pytest.raises(ReglaDeNegocioViolada, match="FallaYaReportada"):
            s.reportar_falla_conexion("T-1", durante)
        presencial, durante_p = en_curso(ventana, modalidad=Modalidad.PRESENCIAL, sede_id="SEDE")
        with pytest.raises(ReglaDeNegocioViolada, match="SoloSesionesEnLinea"):
            presencial.reportar_falla_conexion("E-1", durante_p)

    def test_reconexion_tras_cancelar_es_transicion_invalida(self, ventana):
        s, durante = en_curso(ventana)
        s.reportar_falla_conexion("E-1", durante)
        s.estado = EstadoSesion.CANCELADA
        with pytest.raises(TransicionInvalida):
            s.registrar_reconexion(durante, PARAMS)


def test_servicio_extiende_bloque_y_detecta_empalme(con_tutor, reloj):
    # B-1: mañana 12:00-13:00 y B-2: 14:00-16:00 (ver conftest)
    con_tutor.reserva.reservar_sesion(SolicitudReserva("S-1", "E-1", "T-1", "B-1"))
    con_tutor.reserva.confirmar_pago_reserva("S-1", Dinero("350.00"))
    reloj.momento = AHORA + timedelta(days=1, minutes=30)
    s = con_tutor.ejecucion.extender_sesion("S-1", "E-1", 60, Dinero("350.00"))
    assert s.ventana.fin == AHORA + timedelta(days=1, hours=2)
    with con_tutor.reserva.fabrica_uow() as uow:
        assert uow.agendas.obtener_del_tutor("T-1").bloques["B-1"].ventana.fin == s.ventana.fin
    reloj.momento = AHORA
    con_tutor.reserva.reservar_sesion(SolicitudReserva("S-2", "E-2", "T-1", "B-2"))
    con_tutor.reserva.confirmar_pago_reserva("S-2", Dinero("700.00"))
    inicio_b2 = AHORA + timedelta(days=1, hours=2)
    con_tutor.agenda.agregar_bloque("T-1", "B-4",
                                    VentanaHoraria(inicio_b2 + timedelta(hours=2), inicio_b2 + timedelta(hours=3)))
    reloj.momento = inicio_b2 + timedelta(minutes=10)
    with pytest.raises(ConflictoDeRecurso, match="ExtensionEmpalmada"):
        con_tutor.ejecucion.extender_sesion("S-2", "E-2", 15, Dinero("87.50"))
    con_tutor.ejecucion.reportar_falla_conexion("S-2", "T-1")
    reloj.momento += timedelta(minutes=20)
    assert con_tutor.ejecucion.registrar_reconexion("S-2").estado == EstadoSesion.EN_REVISION


def test_api_extension_y_falla(reloj):
    settings = Settings(database_url="sqlite://", permitir_fecha_simulada=True)
    inicio = AHORA + timedelta(days=1)
    with TestClient(create_app(settings, construir_contenedor(settings)),
                    headers={"X-Fecha-Simulada": AHORA.isoformat()}) as c:
        c.post("/tutores", json={"tutor_id": "T-1", "nombre": "T", "tarifa_hora": "300.00"})
        c.post("/tutores/T-1/bloques", json={"bloque_id": "B-1", "inicio": inicio.isoformat(),
                                             "fin": (inicio + timedelta(hours=1)).isoformat()})
        c.post("/sesiones", json={"sesion_id": "S-1", "estudiante_id": "E-1", "tutor_id": "T-1", "bloque_id": "B-1"})
        c.post("/sesiones/S-1/pago", json={"monto": "300.00"})
        durante = {"X-Fecha-Simulada": (inicio + timedelta(minutes=40)).isoformat()}
        ext = {"estudiante_id": "E-1", "minutos": 30, "monto": "150.00"}
        r = c.post("/sesiones/S-1/extension", json=ext, headers=durante)
        assert r.status_code == 200 and r.json()["monto"] == "450.00" and r.json()["minutos_extension"] == 30
        ext = {"estudiante_id": "E-1", "minutos": 10, "monto": "50.00"}
        r = c.post("/sesiones/S-1/extension", json=ext, headers=durante)
        assert r.status_code == 400 and r.json()["codigo"] == "ExtensionInvalida"
        r = c.post("/sesiones/S-1/falla-conexion", json={"solicitante_id": "T-1"}, headers=durante)
        assert r.status_code == 200 and r.json()["falla_conexion_desde"]
        despues = {"X-Fecha-Simulada": (inicio + timedelta(minutes=50)).isoformat()}
        r = c.post("/sesiones/S-1/reconexion", headers=despues)
        assert r.json()["estado"] == "Confirmada" and r.json()["falla_conexion_desde"] is None
        assert c.post("/sesiones/S-1/reconexion", headers=despues).status_code == 422


def test_migracion_agrega_columnas_a_una_base_existente(tmp_path):
    url = f"sqlite:///{tmp_path / 'vieja.db'}"
    engine = create_engine(url)
    with engine.begin() as conn:  # tabla con el esquema anterior (sin las columnas de US-12/13)
        conn.execute(text("CREATE TABLE sesiones (sesion_id VARCHAR(40) PRIMARY KEY, version INTEGER)"))
    crear_esquema(engine)
    columnas = {c["name"] for c in inspect(engine).get_columns("sesiones")}
    assert {"minutos_extension", "falla_conexion_desde"} <= columnas
    crear_esquema(engine)  # idempotente
