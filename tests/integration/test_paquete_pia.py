"""Paquete de datos del PIA: 120 casos de prueba y 20 transiciones ejecutados por el dominio real."""
from collections import Counter
from decimal import Decimal

import pytest

from conftest import PAQUETE
from infrastructure.paquete_pia import (
    BENEFICIO_REFERENCIA,
    PUEDE_PROCESARSE,
    cargar_paquete,
    ejecutar_casos,
    ejecutar_transiciones,
    escribir_resultados,
)


@pytest.fixture(scope="module")
def operaciones():
    return cargar_paquete(PAQUETE)


def test_carga_con_claves_foraneas(operaciones):
    assert len(operaciones) == 60
    assert sum(len(o.lineas) for o in operaciones.values()) == 117


def test_total_con_decimal(operaciones):
    # AUL-O001: P009 973.00 x 3 + P014 1328.00 x 4 = 8231.00
    assert operaciones["AUL-O001"].total.monto == Decimal("8231.00")
    assert operaciones["AUL-O013"].total.monto == Decimal("0.00")


@pytest.mark.parametrize("op_id, motivo", [
    ("AUL-O001", None),
    ("AUL-O013", "OperacionSinLineas"),
    ("AUL-O008", "PagoNoAutorizado"),
    ("AUL-O034", "EstudianteInactivo"),
])
def test_regla_puede_procesarse(operaciones, op_id, motivo):
    assert PUEDE_PROCESARSE.motivo_de_falla(operaciones[op_id]) == motivo


@pytest.mark.parametrize("op_id, aplica", [
    ("AUL-O003", False),   # preferente pero total 1399 < 1500 (frontera)
    ("AUL-O018", False),   # preferente, total alto, pero con promoción (NOT)
    ("AUL-O023", True),    # preferente, 6974, sin promoción
    ("AUL-O001", False),   # no preferente
])
def test_regla_beneficio_referencia(operaciones, op_id, aplica):
    assert BENEFICIO_REFERENCIA.es_satisfecha_por(operaciones[op_id]) is aplica


def test_ejecuta_los_120_casos(tmp_path):
    resultados = ejecutar_casos(PAQUETE)
    assert len(resultados) == 120
    conteo = Counter(r.resultado for r in resultados)
    assert conteo == {"APROBADA": 46, "RECHAZADA": 14, "APLICA": 9, "NO_APLICA": 51}
    escribir_resultados(tmp_path / "casos.csv", resultados)
    assert (tmp_path / "casos.csv").read_text(encoding="utf-8-sig").count("\n") == 121


def test_ejecuta_las_20_transiciones():
    resultados = {r.caso_id: r for r in ejecutar_transiciones(PAQUETE)}
    assert len(resultados) == 20
    assert resultados["AUL-S001"].resultado == "FINALIZADA"
    assert resultados["AUL-S002"].resultado == "CANCELADA"
    assert resultados["AUL-S003"].resultado == "EXCEPCION:TransicionInvalida"   # repetir aprobación
    assert resultados["AUL-S004"].resultado == "EXCEPCION:TransicionInvalida"   # saltar estado
    assert resultados["AUL-S005"].resultado == "INSCRITA"
    assert resultados["AUL-S008"].resultado == "EXCEPCION:ReglaDeNegocioViolada"  # no autorizada
    assert "OperacionSinLineas" in resultados["AUL-S013"].evidencia
    assert "SesionCompletada" in resultados["AUL-S001"].evidencia
