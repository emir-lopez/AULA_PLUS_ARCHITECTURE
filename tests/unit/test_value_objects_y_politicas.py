"""Value Objects y Domain Services: invariantes, redondeo y fronteras de la política de reembolso."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from domain.exceptions import DatoInvalido
from domain.policies import CalculadoraReembolso, PoliticaCompensacion, PoliticaSuspension
from domain.sede import Sede
from domain.value_objects import (
    Calificacion,
    DesgloseFinanciero,
    Dinero,
    EvidenciaAsistencia,
    Modalidad,
    PorcentajeComision,
    VentanaHoraria,
)

INICIO = datetime(2026, 11, 20, 16, tzinfo=UTC)


class TestDinero:
    def test_redondea_a_centavos_con_half_up(self):
        assert Dinero(Decimal("10.005")).monto == Decimal("10.01")

    def test_float_no_hereda_imprecision(self):
        assert Dinero(0.1).sumar(Dinero(0.2)) == Dinero("0.30")

    @pytest.mark.parametrize("valor", ["-0.01", "-100"])
    def test_rechaza_negativos(self, valor):
        with pytest.raises(DatoInvalido, match="MontoNegativo"):
            Dinero(valor)

    @pytest.mark.parametrize("valor", ["abc", "Infinity"])
    def test_rechaza_no_numericos_o_infinitos(self, valor):
        with pytest.raises(DatoInvalido, match="MontoInvalido"):
            Dinero(valor)

    def test_solo_mxn(self):
        with pytest.raises(DatoInvalido, match="MonedaNoSoportada"):
            Dinero("10", "USD")

    def test_centavos_ida_y_vuelta(self):
        assert Dinero.desde_centavos(Dinero("99.99").centavos) == Dinero("99.99")

    def test_multiplicar_valida_cantidad(self):
        assert Dinero("405.00").multiplicar(3) == Dinero("1215.00")
        with pytest.raises(DatoInvalido):
            Dinero("1").multiplicar(0)

    def test_restar_por_debajo_de_cero_falla(self):
        with pytest.raises(DatoInvalido):
            Dinero("1").restar(Dinero("2"))

    def test_str(self):
        assert str(Dinero("5")) == "5.00 MXN"


class TestDesgloseFinanciero:
    @pytest.mark.parametrize("bruto, comision, neto", [
        ("100.00", "20.00", "80.00"),
        ("350.00", "70.00", "280.00"),
        ("99.99", "20.00", "79.99"),   # 19.998 redondea a 20.00 (no truncar)
        ("0.01", "0.00", "0.01"),
    ])
    def test_r01_comision_20_por_ciento_y_suma_exacta(self, bruto, comision, neto):
        d = DesgloseFinanciero.calcular(Dinero(bruto))
        assert (d.comision, d.neto_tutor) == (Dinero(comision), Dinero(neto))
        assert d.comision.sumar(d.neto_tutor) == d.bruto

    def test_porcentaje_fuera_de_rango(self):
        with pytest.raises(DatoInvalido):
            PorcentajeComision(Decimal("1.5"))


class TestVentanaHoraria:
    def test_exige_zona_horaria(self):
        with pytest.raises(DatoInvalido, match="FechaSinZonaHoraria"):
            VentanaHoraria(datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11))

    def test_fin_despues_de_inicio(self):
        with pytest.raises(DatoInvalido, match="VentanaInvalida"):
            VentanaHoraria(INICIO, INICIO)

    def test_empalme_y_contencion(self):
        a = VentanaHoraria(INICIO, INICIO + timedelta(hours=2))
        b = VentanaHoraria(INICIO + timedelta(hours=1), INICIO + timedelta(hours=3))
        c = VentanaHoraria(INICIO + timedelta(hours=2), INICIO + timedelta(hours=3))
        assert a.se_empalma(b) and not a.se_empalma(c)
        assert a.contiene(VentanaHoraria(INICIO, INICIO + timedelta(hours=1)))
        assert a.duracion == timedelta(hours=2)


class TestEvidencia:
    def test_en_linea_requiere_ambas_conexiones_y_confirmacion_mutua(self):
        completa = EvidenciaAsistencia(INICIO, INICIO, False, True, True)
        assert completa.es_suficiente(Modalidad.EN_LINEA)
        assert not EvidenciaAsistencia(INICIO, None, False, True, True).es_suficiente(Modalidad.EN_LINEA)
        assert not EvidenciaAsistencia(INICIO, INICIO, False, True, False).es_suficiente(Modalidad.EN_LINEA)

    def test_presencial_requiere_checkin_en_geocerca(self):
        assert EvidenciaAsistencia(None, None, True, True, True).es_suficiente(Modalidad.PRESENCIAL)
        assert not EvidenciaAsistencia(INICIO, INICIO, False, True, True).es_suficiente(Modalidad.PRESENCIAL)


@pytest.mark.parametrize("puntos", [0, 6, "5"])
def test_calificacion_fuera_de_rango(puntos):
    with pytest.raises(DatoInvalido):
        Calificacion(puntos)


def test_sede_cupo_positivo():
    with pytest.raises(DatoInvalido):
        Sede("S", "Sala", 0)


class TestCalculadoraReembolso:
    """R-06 / US-07. Fronteras: >24 h = 100 %, 6..24 h = 50 %, <6 h = 0 %."""

    @pytest.mark.parametrize("horas_antes, esperado", [
        (48, "200.00"),
        (24.01, "200.00"),
        (24, "100.00"),      # frontera exacta: ya no es "más de 24 h"
        (12, "100.00"),
        (6, "100.00"),       # frontera exacta incluida en 50 %
        (5.99, "0.00"),
        (0.5, "0.00"),
    ])
    def test_tabla_de_reembolso(self, horas_antes, esperado):
        ahora = INICIO - timedelta(hours=horas_antes)
        assert CalculadoraReembolso().calcular(Dinero("200.00"), INICIO, ahora) == Dinero(esperado)

    def test_exige_fechas_con_zona(self):
        with pytest.raises(DatoInvalido):
            CalculadoraReembolso().porcentaje(INICIO, datetime(2026, 11, 19))


def test_compensacion_total_y_suspension():
    assert PoliticaCompensacion().calcular(Dinero("350")) == Dinero("350")
    politica = PoliticaSuspension(3)
    assert [politica.debe_suspender(n) for n in (1, 2, 3, 4)] == [False, False, True, True]
