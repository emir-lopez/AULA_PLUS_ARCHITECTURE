"""Ejecutar desde la raíz con PYTHONPATH=src; sin paquetes externos."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from aulaplus.cqrs import (
    ConfirmarPagoReservaCommand, ConfirmarPagoReservaCommandHandler,
    ObtenerDetalleSesionQuery, ObtenerDetalleSesionQueryHandler,
    ReservarSesionCommand, ReservarSesionCommandHandler,
)
from aulaplus.domain import AgendaTutor, BloqueDeAgenda, Dinero, VentanaHoraria
from aulaplus.memory import AlmacenMemoria, LecturasMemoria, RelojFijo
from aulaplus.services import ServicioReservaSesion, SolicitudReserva


def main() -> None:
    ahora = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    reloj = RelojFijo(ahora)
    almacen = AlmacenMemoria()
    ventana = VentanaHoraria(ahora + timedelta(days=1), ahora + timedelta(days=1, hours=1))
    almacen.agendas["T-01"] = AgendaTutor("T-01", ahora, {"B-01": BloqueDeAgenda("B-01", ventana)})
    servicio = ServicioReservaSesion(almacen.unidad_de_trabajo, reloj)
    reserva = ReservarSesionCommandHandler(servicio).ejecutar(
        ReservarSesionCommand(SolicitudReserva("S-01", "E-01", "T-01", "B-01", Dinero(Decimal("500"))))
    )
    print("Reserva:", reserva)
    estado = ConfirmarPagoReservaCommandHandler(servicio).ejecutar(
        ConfirmarPagoReservaCommand("S-01", Dinero(Decimal("500")))
    )
    print("Pago:", estado)
    detalle = ObtenerDetalleSesionQueryHandler(LecturasMemoria(almacen)).ejecutar(
        ObtenerDetalleSesionQuery("S-01", "E-01")
    )
    print("Consulta:", detalle)
    print("Eventos pendientes:", [e.nombre for e in almacen.eventos_pendientes])


if __name__ == "__main__":
    main()
