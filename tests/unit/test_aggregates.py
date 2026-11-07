"""Aggregates TransaccionSesion y AgendaTutor: reglas del BRD, fronteras y eventos.

Cada prueba indica la historia de usuario o regla que verifica (trazabilidad).
"""
from datetime import timedelta
from decimal import Decimal

import pytest

from conftest import AHORA, nueva_sesion
from domain.agenda import AgendaTutor
from domain.exceptions import (
    ConflictoDeRecurso,
    DatoInvalido,
    RecursoNoEncontrado,
    ReglaDeNegocioViolada,
    TransicionInvalida,
)
from domain.policies import CalculadoraReembolso, ParametrosOperacion, PoliticaCompensacion, PoliticaSuspension
from domain.state_machine import EstadoBloque, EstadoPago, EstadoSesion
from domain.value_objects import Calificacion, Dinero, EvidenciaAsistencia, Modalidad, ParteSesion, VentanaHoraria

PARAMS = ParametrosOperacion()
EVIDENCIA_OK = EvidenciaAsistencia(AHORA, AHORA, True, True, True)


def nombres(agregado):
    return [e.nombre for e in agregado.eventos]


def confirmada(ventana):
    s = nueva_sesion(ventana)
    s.confirmar_pago(Dinero("350.00"), AHORA + timedelta(minutes=5))
    return s


def completada(ventana):
    s = confirmada(ventana)
    s.completar_con_evidencia(EVIDENCIA_OK, ventana.fin)
    return s


class TestReservaYPago:
    def test_us02_reservar_congela_10_minutos(self, sesion):
        assert sesion.estado == EstadoSesion.RESERVADA
        assert sesion.congelado_hasta == AHORA + timedelta(minutes=10)
        assert nombres(sesion) == ["SesionReservada"]

    def test_presencial_requiere_sede_y_tarifa_positiva(self, ventana):
        with pytest.raises(DatoInvalido, match="SedeRequerida"):
            nueva_sesion(ventana, modalidad=Modalidad.PRESENCIAL)
        with pytest.raises(DatoInvalido, match="MontoInvalido"):
            nueva_sesion(ventana, monto="0")

    def test_us03_pago_integro_confirma(self, sesion):
        sesion.confirmar_pago(Dinero("350.00"), AHORA + timedelta(minutes=9))
        assert (sesion.estado, sesion.estado_pago) == (EstadoSesion.CONFIRMADA, EstadoPago.CONFIRMADO)
        assert nombres(sesion)[-2:] == ["PagoConfirmado", "SesionConfirmada"]

    def test_r03_limite_inclusivo_minuto_10_exacto(self, sesion):
        sesion.confirmar_pago(Dinero("350.00"), AHORA + timedelta(minutes=10))
        assert sesion.estado == EstadoSesion.CONFIRMADA

    def test_r03_un_segundo_despues_se_rechaza_sin_cambios(self, sesion):
        with pytest.raises(ReglaDeNegocioViolada, match="CongelamientoVencido"):
            sesion.confirmar_pago(Dinero("350.00"), AHORA + timedelta(minutes=10, seconds=1))
        assert sesion.estado == EstadoSesion.RESERVADA and nombres(sesion) == ["SesionReservada"]

    def test_monto_incompleto_se_rechaza(self, sesion):
        with pytest.raises(ReglaDeNegocioViolada, match="MontoDePagoIncorrecto"):
            sesion.confirmar_pago(Dinero("349.99"), AHORA)
        assert sesion.estado_pago == EstadoPago.PENDIENTE

    def test_doble_confirmacion_es_transicion_invalida(self, sesion):
        sesion.confirmar_pago(Dinero("350.00"), AHORA)
        with pytest.raises(TransicionInvalida):
            sesion.confirmar_pago(Dinero("350.00"), AHORA)
        assert nombres(sesion).count("PagoConfirmado") == 1

    def test_h13_pago_fallido_conserva_reserva_para_reintento(self, sesion):
        sesion.registrar_pago_fallido("Fondos insuficientes", AHORA + timedelta(minutes=2))
        assert sesion.estado == EstadoSesion.RESERVADA and sesion.intentos_pago_fallidos == 1
        sesion.confirmar_pago(Dinero("350.00"), AHORA + timedelta(minutes=3))
        assert sesion.estado == EstadoSesion.CONFIRMADA
        with pytest.raises(TransicionInvalida):
            sesion.registrar_pago_fallido("x", AHORA)

    def test_pago_fallido_tras_vencer_se_rechaza(self, sesion):
        with pytest.raises(ReglaDeNegocioViolada, match="CongelamientoVencido"):
            sesion.registrar_pago_fallido("x", AHORA + timedelta(minutes=11))

    def test_expirar_solo_despues_del_vencimiento(self, sesion):
        assert sesion.expirar_congelamiento(AHORA + timedelta(minutes=10)) is False
        assert sesion.expirar_congelamiento(AHORA + timedelta(minutes=10, seconds=1)) is True
        assert sesion.estado == EstadoSesion.CANCELADA
        assert sesion.expirar_congelamiento(AHORA + timedelta(hours=1)) is False


class TestCancelacion:
    @pytest.mark.parametrize("horas_antes, reembolso, estado_pago", [
        (30, "350.00", EstadoPago.REEMBOLSADO),
        (12, "175.00", EstadoPago.REEMBOLSO_PARCIAL),
        (2, "0.00", EstadoPago.CONFIRMADO),
    ])
    def test_us07_reembolso_segun_anticipacion(self, ventana, horas_antes, reembolso, estado_pago):
        s = confirmada(ventana)
        monto = s.cancelar_por_estudiante("E-1", ventana.inicio - timedelta(hours=horas_antes), CalculadoraReembolso())
        assert monto == Dinero(reembolso) and s.estado_pago == estado_pago
        assert s.estado == EstadoSesion.CANCELADA
        assert nombres(s)[-2:] == ["SesionCancelada", "ReembolsoCalculado"]

    def test_solo_el_estudiante_y_antes_del_inicio(self, ventana):
        s = confirmada(ventana)
        with pytest.raises(ReglaDeNegocioViolada, match="SolicitanteNoEsElEstudiante"):
            s.cancelar_por_estudiante("E-OTRO", AHORA, CalculadoraReembolso())
        with pytest.raises(ReglaDeNegocioViolada, match="SesionYaInicio"):
            s.cancelar_por_estudiante("E-1", ventana.inicio, CalculadoraReembolso())

    def test_reserva_sin_pagar_no_se_cancela_por_estudiante(self, sesion):
        with pytest.raises(TransicionInvalida):
            sesion.cancelar_por_estudiante("E-1", AHORA, CalculadoraReembolso())

    @pytest.mark.parametrize("horas_antes, tardia", [(30, False), (24, True), (1, True)])
    def test_us08_tutor_cancela_compensacion_total(self, ventana, horas_antes, tardia):
        s = confirmada(ventana)
        monto, es_tardia = s.cancelar_por_tutor("T-1", ventana.inicio - timedelta(hours=horas_antes),
                                                PoliticaCompensacion())
        assert monto == Dinero("350.00") and es_tardia is tardia
        assert s.estado_pago == EstadoPago.REEMBOLSADO

    def test_cancelacion_tutor_validaciones(self, ventana):
        s = confirmada(ventana)
        with pytest.raises(ReglaDeNegocioViolada, match="SolicitanteNoEsElTutor"):
            s.cancelar_por_tutor("E-1", AHORA, PoliticaCompensacion())
        with pytest.raises(ReglaDeNegocioViolada, match="SesionYaInicio"):
            s.cancelar_por_tutor("T-1", ventana.inicio, PoliticaCompensacion())


class TestEjecucion:
    def test_us19_completar_calcula_comision(self, ventana):
        s = completada(ventana)
        assert s.estado == EstadoSesion.COMPLETADA and s.completada_en == ventana.fin
        assert (s.desglose.comision, s.desglose.neto_tutor) == (Dinero("70.00"), Dinero("280.00"))

    def test_no_se_completa_antes_de_terminar(self, ventana):
        s = confirmada(ventana)
        with pytest.raises(ReglaDeNegocioViolada, match="SesionNoFinalizada"):
            s.completar_con_evidencia(EVIDENCIA_OK, ventana.fin - timedelta(minutes=1))

    def test_us06_evidencia_insuficiente_va_a_revision(self, ventana):
        s = confirmada(ventana)
        estado = s.completar_con_evidencia(EvidenciaAsistencia(conexion_tutor=AHORA), ventana.fin)
        assert estado == EstadoSesion.EN_REVISION and s.motivo_revision == "EvidenciaInsuficiente"
        s.resolver_revision(ParteSesion.TUTOR, "Logs de conexión verificados", ventana.fin + timedelta(hours=1))
        assert s.estado == EstadoSesion.COMPLETADA and s.desglose is not None

    def test_us15_no_show_tras_tolerancia_de_10_minutos(self, ventana):
        s = confirmada(ventana)
        with pytest.raises(ReglaDeNegocioViolada, match="ToleranciaNoCumplida"):
            s.registrar_no_show(ParteSesion.TUTOR, ventana.inicio + timedelta(minutes=9), PARAMS,
                                PoliticaCompensacion())
        reembolso = s.registrar_no_show(ParteSesion.TUTOR, ventana.inicio + timedelta(minutes=10), PARAMS,
                                        PoliticaCompensacion())
        assert reembolso == Dinero("350.00") and s.estado == EstadoSesion.NO_SHOW
        assert s.estado_pago == EstadoPago.REEMBOLSADO

    def test_no_show_del_estudiante_sin_reembolso(self, ventana):
        s = confirmada(ventana)
        reembolso = s.registrar_no_show(ParteSesion.ESTUDIANTE, ventana.inicio + timedelta(minutes=15), PARAMS,
                                        PoliticaCompensacion())
        assert reembolso == Dinero.cero() and s.estado_pago == EstadoPago.CONFIRMADO

    def test_us18_calificar(self, ventana):
        s = completada(ventana)
        with pytest.raises(ReglaDeNegocioViolada, match="SolicitanteNoEsElEstudiante"):
            s.calificar("T-1", Calificacion(5), AHORA)
        s.calificar("E-1", Calificacion(5, "Excelente"), ventana.fin)
        with pytest.raises(ReglaDeNegocioViolada, match="SesionYaCalificada"):
            s.calificar("E-1", Calificacion(4), ventana.fin)

    def test_no_se_califica_sin_completar(self, ventana):
        with pytest.raises(ReglaDeNegocioViolada, match="SesionNoCompletada"):
            confirmada(ventana).calificar("E-1", Calificacion(5), AHORA)


class TestDisputaYLiquidacion:
    def test_cu04_disputa_con_plazo_de_72_horas(self, ventana):
        s = completada(ventana)
        d = s.abrir_disputa("E-1", "No se impartió el tema", ventana.fin + timedelta(hours=1), PARAMS)
        assert s.estado == EstadoSesion.EN_REVISION
        assert d.fecha_limite == ventana.fin + timedelta(hours=73)

    @pytest.mark.parametrize("solicitante, motivo, horas, codigo", [
        ("X-9", "motivo", 1, "SolicitanteNoEsParteDeLaSesion"),
        ("E-1", "   ", 1, "MotivoRequerido"),
        ("E-1", "motivo", 49, "VentanaDeDisputaCerrada"),
    ])
    def test_validaciones_de_disputa(self, ventana, solicitante, motivo, horas, codigo):
        s = completada(ventana)
        with pytest.raises((ReglaDeNegocioViolada, DatoInvalido), match=codigo):
            s.abrir_disputa(solicitante, motivo, ventana.fin + timedelta(hours=horas), PARAMS)

    def test_una_sola_disputa_abierta(self, ventana):
        s = completada(ventana)
        s.abrir_disputa("E-1", "a", ventana.fin, PARAMS)
        with pytest.raises(ReglaDeNegocioViolada, match="DisputaYaAbierta"):
            s.abrir_disputa("T-1", "b", ventana.fin, PARAMS)

    def test_r05_disputa_detiene_liberacion(self, ventana):
        s = completada(ventana)
        s.abrir_disputa("E-1", "motivo", ventana.fin + timedelta(hours=1), PARAMS)
        with pytest.raises(ReglaDeNegocioViolada, match="DisputaAbierta"):
            s.liberar_fondos(ventana.fin + timedelta(hours=50), PARAMS)
        assert s.estado_pago == EstadoPago.CONFIRMADO

    def test_resolucion_a_favor_del_tutor_permite_liberar(self, ventana):
        s = completada(ventana)
        s.abrir_disputa("E-1", "motivo", ventana.fin + timedelta(hours=1), PARAMS)
        s.resolver_revision(ParteSesion.TUTOR, "Evidencia válida", ventana.fin + timedelta(hours=20))
        assert s.disputa.abierta is False and s.estado == EstadoSesion.COMPLETADA
        desglose = s.liberar_fondos(ventana.fin + timedelta(hours=48), PARAMS)
        assert desglose.neto_tutor == Dinero("280.00") and s.estado_pago == EstadoPago.LIBERADO
        assert nombres(s)[-1] == "FondosLiberados"

    def test_resolucion_a_favor_del_estudiante_reembolsa(self, ventana):
        s = completada(ventana)
        s.abrir_disputa("E-1", "motivo", ventana.fin, PARAMS)
        s.resolver_revision(ParteSesion.ESTUDIANTE, "Tutor ausente", ventana.fin + timedelta(hours=2))
        assert s.estado == EstadoSesion.CANCELADA and s.estado_pago == EstadoPago.REEMBOLSADO
        with pytest.raises(DatoInvalido):
            s.resolver_revision(ParteSesion.TUTOR, "", ventana.fin)

    def test_us17_retencion_de_48_horas(self, ventana):
        s = completada(ventana)
        with pytest.raises(ReglaDeNegocioViolada, match="RetencionVigente"):
            s.liberar_fondos(ventana.fin + timedelta(hours=47, minutes=59), PARAMS)
        s.liberar_fondos(ventana.fin + timedelta(hours=48), PARAMS)
        with pytest.raises(ReglaDeNegocioViolada, match="PagoNoConfirmado"):
            s.liberar_fondos(ventana.fin + timedelta(hours=49), PARAMS)

    def test_extraer_eventos_vacia_la_lista(self, sesion):
        assert [e.nombre for e in sesion.extraer_eventos()] == ["SesionReservada"] and sesion.eventos == []


class TestAgendaTutor:
    def test_inv_at01_sin_empalmes_ni_duplicados(self, agenda, ventana):
        with pytest.raises(ConflictoDeRecurso, match="BloqueDuplicado"):
            agenda.agregar_bloque("B-1", ventana, AHORA)
        with pytest.raises(ConflictoDeRecurso, match="BloqueEmpalmado"):
            agenda.agregar_bloque("B-2", VentanaHoraria(ventana.inicio + timedelta(minutes=30),
                                                        ventana.fin + timedelta(minutes=30)), AHORA)

    def test_ciclo_disponible_congelado_bloqueado_disponible(self, agenda):
        agenda.congelar_bloque("B-1", "S-1", AHORA)
        assert not agenda.bloque_esta_disponible("B-1")
        with pytest.raises(TransicionInvalida):
            agenda.congelar_bloque("B-1", "S-2", AHORA)
        with pytest.raises(ConflictoDeRecurso, match="HorarioNoDisponible"):
            agenda.bloquear_bloque("B-1", "S-OTRA", AHORA)
        agenda.bloquear_bloque("B-1", "S-1", AHORA)
        assert agenda.bloques["B-1"].estado == EstadoBloque.BLOQUEADO
        agenda.liberar_bloque("B-1", "S-1", AHORA)
        assert agenda.bloques["B-1"].estado == EstadoBloque.DISPONIBLE and agenda.bloques["B-1"].sesion_id is None
        assert [e.nombre for e in agenda.extraer_eventos()] == [
            "HorarioCongelado", "HorarioBloqueado", "HorarioLiberado"]

    def test_bloque_inexistente(self, agenda):
        with pytest.raises(RecursoNoEncontrado):
            agenda.bloque("NO")

    def test_us09_tercera_marca_suspende(self, agenda):
        politica = PoliticaSuspension(3)
        for _ in range(3):
            agenda.registrar_incumplimiento("NoShow", AHORA, politica)
        assert agenda.suspendido and agenda.marcas_incumplimiento == 3
        assert [e.nombre for e in agenda.eventos].count("TutorSuspendido") == 1
        agenda.registrar_incumplimiento("NoShow", AHORA, politica)
        assert [e.nombre for e in agenda.eventos].count("TutorSuspendido") == 1
        with pytest.raises(DatoInvalido):
            agenda.registrar_incumplimiento(" ", AHORA, politica)

    def test_fecha_de_actualizacion_con_zona(self):
        from datetime import datetime
        with pytest.raises(DatoInvalido):
            AgendaTutor("T", "n", "1", datetime(2026, 1, 1))

    def test_monto_reembolso_no_supera_pago(self, ventana):
        s = confirmada(ventana)
        with pytest.raises(ReglaDeNegocioViolada, match="ReembolsoMayorAlPago"):
            s._aplicar_reembolso(Dinero(Decimal("351")))
