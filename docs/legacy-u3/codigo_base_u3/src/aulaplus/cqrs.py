"""CQRS básico: dos Commands de escritura y dos Queries con DTOs propios."""
from __future__ import annotations

from dataclasses import dataclass

from .domain import Dinero, VentanaHoraria
from .ports import LecturasAulaPlus, Reloj
from .services import ServicioReservaSesion, SolicitudReserva, ResultadoReserva


@dataclass(frozen=True)
class ReservarSesionCommand:
    solicitud: SolicitudReserva


class ReservarSesionCommandHandler:
    def __init__(self, servicio: ServicioReservaSesion):
        self.servicio = servicio

    def ejecutar(self, command: ReservarSesionCommand) -> ResultadoReserva:
        return self.servicio.reservar_sesion(command.solicitud)


@dataclass(frozen=True)
class ConfirmarPagoReservaCommand:
    sesion_id: str
    monto_pagado: Dinero


class ConfirmarPagoReservaCommandHandler:
    def __init__(self, servicio: ServicioReservaSesion):
        self.servicio = servicio

    def ejecutar(self, command: ConfirmarPagoReservaCommand) -> str:
        return self.servicio.confirmar_pago_reserva(command.sesion_id, command.monto_pagado)


@dataclass(frozen=True)
class ObtenerDetalleSesionQuery:
    sesion_id: str
    usuario_id: str


@dataclass(frozen=True)
class DetalleSesionDTO:
    sesion_id: str
    estudiante_id: str
    tutor_id: str
    estado: str
    estado_pago: str
    monto: str


class ObtenerDetalleSesionQueryHandler:
    def __init__(self, lecturas: LecturasAulaPlus):
        self.lecturas = lecturas

    def ejecutar(self, query: ObtenerDetalleSesionQuery) -> DetalleSesionDTO:
        return DetalleSesionDTO(**self.lecturas.detalle_sesion(query.sesion_id, query.usuario_id))


@dataclass(frozen=True)
class ObtenerTutoresDisponiblesQuery:
    ventana: VentanaHoraria


@dataclass(frozen=True)
class TutorDisponibleDTO:
    tutor_id: str
    bloque_id: str
    inicio: str
    fin: str


class ObtenerTutoresDisponiblesQueryHandler:
    def __init__(self, lecturas: LecturasAulaPlus, reloj: Reloj):
        self.lecturas, self.reloj = lecturas, reloj

    def ejecutar(self, query: ObtenerTutoresDisponiblesQuery) -> list[TutorDisponibleDTO]:
        return [TutorDisponibleDTO(**fila) for fila in
                self.lecturas.tutores_disponibles(query.ventana, self.reloj.ahora())]
