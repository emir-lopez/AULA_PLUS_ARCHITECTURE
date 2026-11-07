"""Specification Pattern (AND/OR/NOT) y matriz completa de la máquina de estados."""
from datetime import UTC, datetime, timedelta

import pytest

from domain.exceptions import ReglaDeNegocioViolada, TransicionInvalida
from domain.specifications import (
    AnticipacionMinimaSpec,
    CandidatoLiberacion,
    CupoDisponibleSpec,
    EsPresencialSpec,
    PerfilVigenteSpec,
    SolicitudDeReserva,
    SpecificationSimple,
    liberacion_permitida,
    reserva_permitida,
)
from domain.state_machine import (
    TRANSICIONES_SESION,
    AccionSesion,
    EstadoBloque,
    EstadoSesion,
    acciones_permitidas,
    transicionar,
    transicionar_bloque,
)

AHORA = datetime(2026, 11, 10, 12, tzinfo=UTC)


def solicitud(**cambios) -> SolicitudDeReserva:
    base = dict(inicio_sesion=AHORA + timedelta(hours=3), ahora=AHORA, agenda_actualizada_en=AHORA,
                tutor_suspendido=False, bloque_disponible=True, es_presencial=False, ocupacion_sede=0, cupo_sede=0)
    base.update(cambios)
    return SolicitudDeReserva(**base)


class TestReservaPermitida:
    def test_caso_feliz_en_linea_no_requiere_cupo(self):
        assert reserva_permitida().es_satisfecha_por(solicitud())

    @pytest.mark.parametrize("cambios, codigo", [
        ({"inicio_sesion": AHORA + timedelta(hours=1, minutes=59)}, "AnticipacionInsuficiente"),
        ({"agenda_actualizada_en": AHORA - timedelta(days=7, seconds=1)}, "PerfilNoVisible"),
        ({"tutor_suspendido": True}, "TutorSuspendido"),
        ({"bloque_disponible": False}, "HorarioNoDisponible"),
        ({"es_presencial": True, "ocupacion_sede": 2, "cupo_sede": 2}, "SinCupoEnSede"),
    ])
    def test_cada_regla_reporta_su_motivo(self, cambios, codigo):
        with pytest.raises(ReglaDeNegocioViolada, match=codigo):
            reserva_permitida().verificar(solicitud(**cambios))

    def test_fronteras_exactas(self):
        assert AnticipacionMinimaSpec(2).es_satisfecha_por(solicitud(inicio_sesion=AHORA + timedelta(hours=2)))
        assert PerfilVigenteSpec(7).es_satisfecha_por(solicitud(agenda_actualizada_en=AHORA - timedelta(days=7)))
        assert reserva_permitida().es_satisfecha_por(solicitud(es_presencial=True, ocupacion_sede=1, cupo_sede=2))

    def test_or_not_presencial_o_cupo(self):
        regla = ~EsPresencialSpec() | CupoDisponibleSpec()
        assert regla.es_satisfecha_por(solicitud(es_presencial=False, cupo_sede=0))
        assert not regla.es_satisfecha_por(solicitud(es_presencial=True, ocupacion_sede=3, cupo_sede=3))
        assert regla.codigo == "NoModalidadNoPresencial|SinCupoEnSede"

    def test_specification_simple_y_verificar_ok(self):
        par = SpecificationSimple("Impar", lambda n: n % 2 == 0)
        par.verificar(4)
        assert (par & ~par).es_satisfecha_por(4) is False
        assert (par | ~par).es_satisfecha_por(3) is True


class TestLiberacionPermitida:
    def candidato(self, **cambios):
        base = dict(sesion_completada=True, pago_confirmado=True, disputa_abierta=False,
                    completada_en=AHORA, ahora=AHORA + timedelta(hours=48))
        base.update(cambios)
        return CandidatoLiberacion(**base)

    def test_libera_exactamente_a_las_48_horas(self):
        assert liberacion_permitida(48).es_satisfecha_por(self.candidato())

    @pytest.mark.parametrize("cambios, codigo", [
        ({"ahora": AHORA + timedelta(hours=47, minutes=59)}, "RetencionVigente"),
        ({"disputa_abierta": True}, "DisputaAbierta"),
        ({"sesion_completada": False}, "SesionNoCompletada"),
        ({"pago_confirmado": False}, "PagoNoConfirmado"),
        ({"completada_en": None}, "RetencionVigente"),
    ])
    def test_motivos_de_rechazo(self, cambios, codigo):
        assert liberacion_permitida(48).motivo_de_falla(self.candidato(**cambios)) == codigo


class TestMaquinaDeEstados:
    def test_tiene_diez_transiciones_validas(self):
        assert len(TRANSICIONES_SESION) == 10

    @pytest.mark.parametrize("estado", list(EstadoSesion))
    @pytest.mark.parametrize("accion", list(AccionSesion))
    def test_matriz_completa_6x10(self, estado, accion):
        if (estado, accion) in TRANSICIONES_SESION:
            assert transicionar(estado, accion) == TRANSICIONES_SESION[(estado, accion)]
        else:
            with pytest.raises(TransicionInvalida):
                transicionar(estado, accion)

    def test_estados_finales_sin_salidas(self):
        assert acciones_permitidas(EstadoSesion.CANCELADA) == []
        assert acciones_permitidas(EstadoSesion.NO_SHOW) == []
        assert AccionSesion.CONFIRMAR_PAGO in acciones_permitidas(EstadoSesion.RESERVADA)

    def test_bloque(self):
        assert transicionar_bloque(EstadoBloque.DISPONIBLE, "congelar") == EstadoBloque.CONGELADO
        assert transicionar_bloque(EstadoBloque.CONGELADO, "bloquear") == EstadoBloque.BLOQUEADO
        with pytest.raises(TransicionInvalida, match="HorarioNoDisponible"):
            transicionar_bloque(EstadoBloque.DISPONIBLE, "bloquear")
