"""Endpoints REST. Cada endpoint: recibe DTO -> llama a un Application Service -> devuelve el Read Model.

No hay reglas de negocio aquí: si se reemplaza FastAPI, domain/ y application/ no cambian.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Request, status

from application.queries import ObtenerDetalleSesionQuery, ObtenerTutoresDisponiblesQuery
from application.services import SolicitudReserva
from domain.sede import Sede
from domain.value_objects import Calificacion, Dinero, EvidenciaAsistencia, VentanaHoraria

from .container import Contenedor
from .schemas import (
    BloqueIn,
    CalificacionIn,
    DisputaIn,
    ErrorOut,
    EvidenciaIn,
    NoShowIn,
    PagoIn,
    ReservaIn,
    ResolucionIn,
    SedeIn,
    SolicitanteIn,
    TutorIn,
)

ERRORES = {
    400: {"model": ErrorOut, "description": "Dato inválido"},
    404: {"model": ErrorOut, "description": "Recurso no encontrado"},
    409: {"model": ErrorOut, "description": "Transición inválida o conflicto de recurso"},
    422: {"model": ErrorOut, "description": "Regla de negocio violada / validación"},
}

router = APIRouter(responses=ERRORES)


def _c(request: Request) -> Contenedor:
    return request.app.state.contenedor


def _detalle(c: Contenedor, sesion_id: str) -> dict:
    return c.consultas.detalle_sesion(ObtenerDetalleSesionQuery(sesion_id))


# ------------------------------------------------------------- catálogo
@router.post("/tutores", status_code=status.HTTP_201_CREATED, tags=["agenda"],
             summary="Registrar tutor y su agenda (NB-02)")
def registrar_tutor(body: TutorIn, request: Request) -> dict:
    agenda = _c(request).agenda.registrar_tutor(body.tutor_id, body.nombre, Dinero(body.tarifa_hora))
    return {"tutor_id": agenda.tutor_id, "nombre": agenda.nombre, "tarifa_hora": agenda.tarifa_hora}


@router.post("/tutores/{tutor_id}/bloques", status_code=status.HTTP_201_CREATED, tags=["agenda"],
             summary="Publicar un bloque de disponibilidad")
def agregar_bloque(tutor_id: str, body: BloqueIn, request: Request) -> dict:
    agenda = _c(request).agenda.agregar_bloque(tutor_id, body.bloque_id, VentanaHoraria(body.inicio, body.fin))
    b = agenda.bloques[body.bloque_id]
    return {"tutor_id": tutor_id, "bloque_id": b.bloque_id, "estado": b.estado.value,
            "inicio": b.ventana.inicio.isoformat(), "fin": b.ventana.fin.isoformat()}


@router.post("/sedes", status_code=status.HTTP_201_CREATED, tags=["agenda"], summary="Registrar sede presencial")
def registrar_sede(body: SedeIn, request: Request) -> dict:
    sede = _c(request).agenda.registrar_sede(Sede(body.sede_id, body.nombre, body.cupo_maximo))
    return {"sede_id": sede.sede_id, "nombre": sede.nombre, "cupo_maximo": sede.cupo_maximo}


@router.get("/tutores/disponibles", tags=["consultas"], summary="Buscar tutores disponibles (US-11)")
def tutores_disponibles(request: Request, inicio: datetime = Query(...), fin: datetime = Query(...)) -> list[dict]:
    return _c(request).consultas.tutores_disponibles(ObtenerTutoresDisponiblesQuery(VentanaHoraria(inicio, fin)))


# ---------------------------------------------------------- CU-01 / CU-02
@router.post("/sesiones", status_code=status.HTTP_201_CREATED, tags=["reserva y pago"],
             summary="CU-01 Reservar sesión (congela el horario 10 min)")
def reservar(body: ReservaIn, request: Request) -> dict:
    c = _c(request)
    sesion = c.reserva.reservar_sesion(SolicitudReserva(
        body.sesion_id, body.estudiante_id, body.tutor_id, body.bloque_id, body.modalidad, body.sede_id))
    return _detalle(c, sesion.sesion_id)


@router.post("/sesiones/{sesion_id}/pago", tags=["reserva y pago"],
             summary="CU-02 Registrar resultado de la pasarela (confirma y bloquea, o registra fallo)")
def pagar(sesion_id: str, body: PagoIn, request: Request) -> dict:
    c = _c(request)
    if body.resultado == "Fallido":
        c.reserva.registrar_pago_fallido(sesion_id, body.motivo or "Rechazado por la pasarela")
    else:
        c.reserva.confirmar_pago_reserva(sesion_id, Dinero(body.monto))
    return _detalle(c, sesion_id)


@router.post("/sesiones/{sesion_id}/expirar", tags=["reserva y pago"],
             summary="CU-02 Vencer el congelamiento (lo dispara un temporizador)")
def expirar(sesion_id: str, request: Request) -> dict:
    c = _c(request)
    expirada = c.reserva.expirar_congelamiento(sesion_id)
    return {"expirada": expirada, **_detalle(c, sesion_id)}


# --------------------------------------------------------------- CU-03
@router.post("/sesiones/{sesion_id}/cancelacion-estudiante", tags=["cancelación"],
             summary="CU-03 Cancelar por el estudiante (reembolso 100/50/0 %)")
def cancelar_estudiante(sesion_id: str, body: SolicitanteIn, request: Request) -> dict:
    c = _c(request)
    c.cancelacion.cancelar_por_estudiante(sesion_id, body.solicitante_id)
    return _detalle(c, sesion_id)


@router.post("/sesiones/{sesion_id}/cancelacion-tutor", tags=["cancelación"],
             summary="Cancelación del tutor: compensación 100 % y marca si es tardía (US-08, US-09)")
def cancelar_tutor(sesion_id: str, body: SolicitanteIn, request: Request) -> dict:
    c = _c(request)
    c.cancelacion.cancelar_por_tutor(sesion_id, body.solicitante_id)
    return _detalle(c, sesion_id)


# ------------------------------------------------------------ ejecución
@router.post("/sesiones/{sesion_id}/completar", tags=["ejecución"],
             summary="Registrar evidencia de asistencia (US-04/05/06) y calcular comisión (US-19)")
def completar(sesion_id: str, body: EvidenciaIn, request: Request) -> dict:
    c = _c(request)
    c.ejecucion.completar_sesion(sesion_id, EvidenciaAsistencia(**body.model_dump()))
    return _detalle(c, sesion_id)


@router.post("/sesiones/{sesion_id}/no-show", tags=["ejecución"], summary="Registrar No-Show (US-15)")
def no_show(sesion_id: str, body: NoShowIn, request: Request) -> dict:
    c = _c(request)
    c.ejecucion.registrar_no_show(sesion_id, body.parte_ausente)
    return _detalle(c, sesion_id)


@router.post("/sesiones/{sesion_id}/calificacion", tags=["ejecución"], summary="Calificar sesión (US-18)")
def calificar(sesion_id: str, body: CalificacionIn, request: Request) -> dict:
    c = _c(request)
    c.ejecucion.calificar(sesion_id, body.estudiante_id, Calificacion(body.puntos, body.comentario))
    return _detalle(c, sesion_id)


# ---------------------------------------------------------- CU-04 / CU-05
@router.post("/sesiones/{sesion_id}/disputa", tags=["disputa y liquidación"],
             summary="CU-04 Abrir disputa (detiene la liberación)")
def abrir_disputa(sesion_id: str, body: DisputaIn, request: Request) -> dict:
    c = _c(request)
    c.disputa.abrir_disputa(sesion_id, body.solicitante_id, body.motivo)
    return _detalle(c, sesion_id)


@router.post("/sesiones/{sesion_id}/resolucion", tags=["disputa y liquidación"],
             summary="Soporte resuelve la revisión o disputa (máx. 72 h)")
def resolver(sesion_id: str, body: ResolucionIn, request: Request) -> dict:
    c = _c(request)
    c.disputa.resolver(sesion_id, body.a_favor_de, body.resolucion)
    return _detalle(c, sesion_id)


@router.post("/sesiones/{sesion_id}/liberacion", tags=["disputa y liquidación"],
             summary="CU-05 Liberar pago neto al tutor (48 h sin disputa)")
def liberar(sesion_id: str, request: Request) -> dict:
    c = _c(request)
    c.liquidacion.liberar_pago_al_tutor(sesion_id)
    return _detalle(c, sesion_id)


# ------------------------------------------------------------ consultas
@router.get("/sesiones/{sesion_id}", tags=["consultas"], summary="Detalle de sesión (Read Model)")
def detalle(sesion_id: str, request: Request) -> dict:
    return _detalle(_c(request), sesion_id)


@router.get("/sesiones/{sesion_id}/eventos", tags=["consultas"], summary="Domain Events de la sesión (outbox)")
def eventos_sesion(sesion_id: str, request: Request) -> list[dict]:
    c = _c(request)
    _detalle(c, sesion_id)  # 404 si no existe
    return c.consultas.eventos(sesion_id)


@router.get("/soporte/disputas", tags=["consultas"], summary="Cola de mediación de Soporte")
def disputas(request: Request) -> list[dict]:
    return _c(request).consultas.disputas_pendientes()


@router.get("/liquidaciones/pendientes", tags=["consultas"], summary="Pagos listos para liberar")
def pendientes(request: Request) -> list[str]:
    return _c(request).consultas.pagos_listos_para_liberar()


@router.get("/indicadores", tags=["consultas"], summary="KPIs del BRD sección 9 (NB-15)")
def indicadores(request: Request) -> dict:
    return _c(request).consultas.indicadores()
