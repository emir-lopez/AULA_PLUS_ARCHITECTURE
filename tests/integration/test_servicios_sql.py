"""Integración Application Services + SQLAlchemy + Unit of Work (SQLite en memoria)."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from application.services import SolicitudReserva
from conftest import AHORA
from domain.exceptions import ConflictoDeRecurso, RecursoNoEncontrado, ReglaDeNegocioViolada, TransicionInvalida
from domain.sede import Sede
from domain.state_machine import EstadoBloque, EstadoPago, EstadoSesion
from domain.value_objects import Dinero, EvidenciaAsistencia, Modalidad, ParteSesion, VentanaHoraria
from infrastructure.db import EventoOutboxRow, SesionRow


def reservar(c, sesion_id="S-1", bloque_id="B-1", **kw):
    return c.reserva.reservar_sesion(SolicitudReserva(sesion_id, kw.pop("estudiante", "E-1"), "T-1", bloque_id, **kw))


def agenda(c):
    with c.reserva.fabrica_uow() as uow:
        return uow.agendas.obtener_del_tutor("T-1")


def detalle(c, sid="S-1"):
    return c.consultas.lecturas.detalle_sesion(sid)


def test_cu01_reserva_atomica_sesion_y_agenda(con_tutor):
    sesion = reservar(con_tutor)
    assert sesion.monto == Dinero("350.00")
    assert detalle(con_tutor)["estado"] == "Reservada"
    assert agenda(con_tutor).bloques["B-1"].estado == EstadoBloque.CONGELADO


def test_tarifa_por_duracion_del_bloque(con_tutor):
    assert reservar(con_tutor, bloque_id="B-2").monto == Dinero("700.00")  # 2 h x 350


def test_rechazo_hace_rollback_completo(con_tutor, reloj):
    reloj.momento = AHORA + timedelta(hours=23)  # el bloque inicia en 1 h: viola R-02
    with pytest.raises(ReglaDeNegocioViolada, match="AnticipacionInsuficiente"):
        reservar(con_tutor)
    assert detalle(con_tutor) == {}
    assert agenda(con_tutor).bloques["B-1"].estado == EstadoBloque.DISPONIBLE


def test_doble_reserva_del_mismo_bloque(con_tutor):
    reservar(con_tutor)
    with pytest.raises(ReglaDeNegocioViolada, match="HorarioNoDisponible"):
        reservar(con_tutor, sesion_id="S-2", estudiante="E-2")
    with pytest.raises(ConflictoDeRecurso, match="SesionDuplicada"):
        reservar(con_tutor, bloque_id="B-2")


def test_cu02_pago_confirma_y_bloquea_y_guarda_eventos_en_outbox(con_tutor):
    reservar(con_tutor)
    con_tutor.reserva.confirmar_pago_reserva("S-1", Dinero("350.00"))
    assert agenda(con_tutor).bloques["B-1"].estado == EstadoBloque.BLOQUEADO
    eventos = [e["nombre"] for e in con_tutor.consultas.eventos("S-1")]
    assert eventos == ["SesionReservada", "PagoConfirmado", "SesionConfirmada"]
    tutor = [e["nombre"] for e in con_tutor.consultas.eventos("T-1")]
    assert tutor[-2:] == ["HorarioCongelado", "HorarioBloqueado"]


def test_cu02_vencimiento_libera_el_bloque(con_tutor, reloj):
    reservar(con_tutor)
    reloj.momento = AHORA + timedelta(minutes=11)
    assert con_tutor.reserva.expirar_congelamiento("S-1") is True
    assert con_tutor.reserva.expirar_congelamiento("S-1") is False
    assert agenda(con_tutor).bloques["B-1"].estado == EstadoBloque.DISPONIBLE
    with pytest.raises(TransicionInvalida):  # ya está Cancelada
        con_tutor.reserva.registrar_pago_fallido("S-1", "tarde")


def test_pago_fallido_se_persiste(con_tutor):
    reservar(con_tutor)
    con_tutor.reserva.registrar_pago_fallido("S-1", "Tarjeta rechazada")
    assert detalle(con_tutor)["intentos_pago_fallidos"] == 1


def test_cu03_cancelacion_estudiante_reembolso_y_bloque_libre(con_tutor):
    reservar(con_tutor)
    con_tutor.reserva.confirmar_pago_reserva("S-1", Dinero("350.00"))
    s = con_tutor.cancelacion.cancelar_por_estudiante("S-1", "E-1")
    assert s.monto_reembolso == Dinero("175.00")  # 24 h antes exactas -> 50 %
    assert detalle(con_tutor)["reembolso"] == "175.00"
    assert agenda(con_tutor).bloques["B-1"].estado == EstadoBloque.DISPONIBLE


def test_cancelacion_tardia_del_tutor_suma_marca(con_tutor):
    reservar(con_tutor)
    con_tutor.reserva.confirmar_pago_reserva("S-1", Dinero("350.00"))
    con_tutor.cancelacion.cancelar_por_tutor("S-1", "T-1")
    assert agenda(con_tutor).marcas_incumplimiento == 1
    assert detalle(con_tutor)["estado_pago"] == EstadoPago.REEMBOLSADO.value


def test_us09_tres_no_show_suspenden_y_ocultan_al_tutor(con_tutor, reloj):
    inicio = AHORA + timedelta(days=1)
    for i in range(3):
        bloque = f"BX-{i}"
        con_tutor.agenda.agregar_bloque("T-1", bloque, VentanaHoraria(inicio + timedelta(hours=5 + i),
                                                                      inicio + timedelta(hours=6 + i)))
        reloj.momento = AHORA
        reservar(con_tutor, sesion_id=f"NS-{i}", bloque_id=bloque)
        con_tutor.reserva.confirmar_pago_reserva(f"NS-{i}", Dinero("350.00"))
        reloj.momento = inicio + timedelta(hours=5 + i, minutes=10)
        con_tutor.ejecucion.registrar_no_show(f"NS-{i}", ParteSesion.TUTOR)
    assert agenda(con_tutor).suspendido
    reloj.momento = AHORA
    from application.queries import ObtenerTutoresDisponiblesQuery
    ventana = VentanaHoraria(inicio, inicio + timedelta(hours=1))
    assert con_tutor.consultas.tutores_disponibles(ObtenerTutoresDisponiblesQuery(ventana)) == []
    with pytest.raises(ReglaDeNegocioViolada, match="TutorSuspendido"):
        reservar(con_tutor)


def test_flujo_completo_hasta_liberacion_y_kpis(con_tutor, reloj):
    reservar(con_tutor)
    con_tutor.reserva.confirmar_pago_reserva("S-1", Dinero("350.00"))
    fin = AHORA + timedelta(days=1, hours=1)
    reloj.momento = fin
    con_tutor.ejecucion.completar_sesion("S-1", EvidenciaAsistencia(fin, fin, False, True, True))
    from domain.value_objects import Calificacion
    con_tutor.ejecucion.calificar("S-1", "E-1", Calificacion(5, "Muy bien"))
    reloj.momento = fin + timedelta(hours=47)
    assert con_tutor.consultas.pagos_listos_para_liberar() == []
    reloj.momento = fin + timedelta(hours=48)
    assert con_tutor.consultas.pagos_listos_para_liberar() == ["S-1"]
    assert con_tutor.liquidacion.liberar_pendientes(["S-1"]) == ["S-1"]
    d = detalle(con_tutor)
    assert (d["estado_pago"], d["comision"], d["neto_tutor"], d["calificacion"]) == ("Liberado", "70.00", "280.00", 5)
    kpi = con_tutor.consultas.indicadores()
    assert kpi["ingreso_comisiones"] == "70.00" and kpi["tasa_completadas"] == 1.0


def test_disputa_y_cola_de_soporte(con_tutor, reloj):
    reservar(con_tutor)
    con_tutor.reserva.confirmar_pago_reserva("S-1", Dinero("350.00"))
    fin = AHORA + timedelta(days=1, hours=1)
    reloj.momento = fin
    con_tutor.ejecucion.completar_sesion("S-1", EvidenciaAsistencia(fin, fin, False, True, True))
    con_tutor.disputa.abrir_disputa("S-1", "E-1", "El tutor terminó antes")
    cola = con_tutor.consultas.disputas_pendientes()
    assert cola[0]["sesion_id"] == "S-1" and cola[0]["fecha_limite"]
    reloj.momento = fin + timedelta(hours=60)
    assert con_tutor.consultas.pagos_listos_para_liberar() == []
    con_tutor.disputa.resolver("S-1", ParteSesion.TUTOR, "Duración verificada")
    assert con_tutor.consultas.pagos_listos_para_liberar() == ["S-1"]


def test_conflicto_de_version_optimista(con_tutor):
    """Dos operaciones leen la misma sesión; la segunda en guardar recibe 409 y revierte."""
    reservar(con_tutor)
    uow_a, uow_b = con_tutor.reserva.fabrica_uow(), con_tutor.reserva.fabrica_uow()
    with uow_a:
        s_a = uow_a.transacciones.obtener("S-1")
        with uow_b:
            s_b = uow_b.transacciones.obtener("S-1")
            s_b.registrar_pago_fallido("b", AHORA)
            uow_b.transacciones.guardar(s_b)
            uow_b.confirmar()
        s_a.registrar_pago_fallido("a", AHORA)
        with pytest.raises(ConflictoDeRecurso, match="ConflictoDeVersion"):
            uow_a.transacciones.guardar(s_a)
    assert detalle(con_tutor)["intentos_pago_fallidos"] == 1


def test_r07_cupo_de_sede_presencial(con_tutor):
    con_tutor.agenda.registrar_sede(Sede("SEDE-1", "Biblioteca", cupo_maximo=1))
    con_tutor.agenda.registrar_tutor("T-2", "Tutor Dos", Dinero("200"))
    inicio = AHORA + timedelta(days=1)
    con_tutor.agenda.agregar_bloque("T-2", "B-9", VentanaHoraria(inicio, inicio + timedelta(hours=1)))
    reservar(con_tutor, modalidad=Modalidad.PRESENCIAL, sede_id="SEDE-1")
    with pytest.raises(ReglaDeNegocioViolada, match="SinCupoEnSede"):
        con_tutor.reserva.reservar_sesion(SolicitudReserva("S-2", "E-2", "T-2", "B-9", Modalidad.PRESENCIAL, "SEDE-1"))
    with pytest.raises(ConflictoDeRecurso):
        con_tutor.agenda.registrar_sede(Sede("SEDE-1", "dup", 3))
    with pytest.raises(RecursoNoEncontrado):
        con_tutor.reserva.reservar_sesion(SolicitudReserva("S-3", "E-3", "T-2", "B-9", Modalidad.PRESENCIAL, "NO"))


def test_recursos_inexistentes_y_duplicados(con_tutor):
    with pytest.raises(RecursoNoEncontrado, match="TutorNoEncontrado"):
        con_tutor.agenda.agregar_bloque("NO", "B", VentanaHoraria(AHORA, AHORA + timedelta(hours=1)))
    with pytest.raises(RecursoNoEncontrado, match="SesionNoEncontrada"):
        con_tutor.reserva.confirmar_pago_reserva("NO", Dinero("1"))
    with pytest.raises(ConflictoDeRecurso, match="TutorDuplicado"):
        con_tutor.agenda.registrar_tutor("T-1", "dup", Dinero("1"))


def test_outbox_no_guarda_eventos_si_la_operacion_falla(con_tutor):
    reservar(con_tutor)
    with pytest.raises(ReglaDeNegocioViolada):
        con_tutor.reserva.confirmar_pago_reserva("S-1", Dinero("1.00"))
    with con_tutor.consultas.lecturas.fabrica() as s:
        nombres = s.scalars(select(EventoOutboxRow.nombre).where(EventoOutboxRow.agregado_id == "S-1")).all()
        assert nombres == ["SesionReservada"]
        assert s.get(SesionRow, "S-1").estado == EstadoSesion.RESERVADA.value
