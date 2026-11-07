"""Menú de práctica para usar AulaPlus desde PowerShell.

El pago es simulado y los datos viven en memoria durante esta ejecución.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from aulaplus.cqrs import (  # noqa: E402
    ConfirmarPagoReservaCommand, ConfirmarPagoReservaCommandHandler,
    ObtenerDetalleSesionQuery, ObtenerDetalleSesionQueryHandler,
    ObtenerTutoresDisponiblesQuery, ObtenerTutoresDisponiblesQueryHandler,
    ReservarSesionCommand, ReservarSesionCommandHandler,
)
from aulaplus.domain import (  # noqa: E402
    AgendaTutor, BloqueDeAgenda, Dinero, ReglaDeNegocio, VentanaHoraria,
)
from aulaplus.memory import AlmacenMemoria, LecturasMemoria  # noqa: E402
from aulaplus.services import ServicioReservaSesion, SolicitudReserva  # noqa: E402


class RelojAjustable:
    def __init__(self) -> None:
        self.desplazamiento = timedelta()

    def ahora(self) -> datetime:
        return datetime.now(timezone.utc).replace(microsecond=0) + self.desplazamiento

    def avanzar(self, minutos: int) -> None:
        self.desplazamiento += timedelta(minutes=minutos)


def preparar_datos(reloj: RelojAjustable) -> tuple[AlmacenMemoria, dict[str, tuple[str, str, Dinero, VentanaHoraria]]]:
    almacen = AlmacenMemoria()
    manana = (reloj.ahora() + timedelta(days=1)).date()
    opciones = {
        "1": ("T-01", "B-01", Dinero(Decimal("500")),
              VentanaHoraria(datetime(manana.year, manana.month, manana.day, 15, tzinfo=timezone.utc),
                             datetime(manana.year, manana.month, manana.day, 16, tzinfo=timezone.utc))),
        "2": ("T-02", "B-02", Dinero(Decimal("400")),
              VentanaHoraria(datetime(manana.year, manana.month, manana.day, 17, tzinfo=timezone.utc),
                             datetime(manana.year, manana.month, manana.day, 18, tzinfo=timezone.utc))),
    }
    for tutor_id, bloque_id, _precio, ventana in opciones.values():
        almacen.agendas[tutor_id] = AgendaTutor(
            tutor_id, reloj.ahora(), {bloque_id: BloqueDeAgenda(bloque_id, ventana)}
        )
    return almacen, opciones


def pedir(etiqueta: str) -> str:
    return input(etiqueta).strip()


def main() -> None:
    reloj = RelojAjustable()
    almacen, opciones = preparar_datos(reloj)
    servicio = ServicioReservaSesion(almacen.unidad_de_trabajo, reloj)
    lectura = LecturasMemoria(almacen)
    reservar = ReservarSesionCommandHandler(servicio)
    pagar = ConfirmarPagoReservaCommandHandler(servicio)
    detalle = ObtenerDetalleSesionQueryHandler(lectura)
    disponibles = ObtenerTutoresDisponiblesQueryHandler(lectura, reloj)
    siguiente_id = 1
    sesiones_creadas: list[str] = []

    print("\nAULAPLUS | Práctica en terminal")
    print("El pago es simulado. Los datos se reinician al cerrar el programa.\n")
    while True:
        print("1 Ver horarios   2 Reservar   3 Simular pago")
        print("4 Ver mi sesión   5 Avanzar 11 min y vencer reservas   0 Salir")
        opcion = pedir("Elige una opción: ")
        try:
            if opcion == "1":
                for numero, (tutor_id, bloque_id, precio, ventana) in opciones.items():
                    lista = disponibles.ejecutar(ObtenerTutoresDisponiblesQuery(ventana))
                    libre = any(x.tutor_id == tutor_id and x.bloque_id == bloque_id for x in lista)
                    estado = "Disponible" if libre else "No disponible"
                    print(f"{numero}. {tutor_id} | {ventana.inicio:%d/%m %H:%M} UTC | ${precio.monto} | {estado}")
            elif opcion == "2":
                numero = pedir("Número del horario (1 o 2): ")
                if numero not in opciones:
                    print("Ese horario no existe.")
                    continue
                estudiante_id = pedir("Tu ID de estudiante [E-01]: ") or "E-01"
                tutor_id, bloque_id, precio, _ventana = opciones[numero]
                sesion_id = f"S-{siguiente_id:02d}"
                resultado = reservar.ejecutar(ReservarSesionCommand(
                    SolicitudReserva(sesion_id, estudiante_id, tutor_id, bloque_id, precio)
                ))
                siguiente_id += 1
                sesiones_creadas.append(sesion_id)
                print(f"Reserva creada: {resultado.sesion_id}, {resultado.estado}.")
                print(f"Paga antes de {resultado.congelado_hasta} para confirmar.")
            elif opcion == "3":
                sesion_id = pedir("ID de sesión (ej. S-01): ")
                estudiante_id = pedir("Tu ID de estudiante [E-01]: ") or "E-01"
                vista = detalle.ejecutar(ObtenerDetalleSesionQuery(sesion_id, estudiante_id))
                texto = pedir(f"Monto a simular [${vista.monto}]: ") or vista.monto
                estado = pagar.ejecutar(ConfirmarPagoReservaCommand(sesion_id, Dinero(Decimal(texto))))
                print(f"Pago simulado. La sesión quedó {estado}.")
            elif opcion == "4":
                sesion_id = pedir("ID de sesión (ej. S-01): ")
                estudiante_id = pedir("Tu ID de estudiante [E-01]: ") or "E-01"
                vista = detalle.ejecutar(ObtenerDetalleSesionQuery(sesion_id, estudiante_id))
                print(f"{vista.sesion_id}: {vista.estado} | pago {vista.estado_pago} | ${vista.monto} | tutor {vista.tutor_id}")
            elif opcion == "5":
                reloj.avanzar(11)
                vencidas = [x for x in sesiones_creadas if servicio.expirar_congelamiento(x)]
                print("Se avanzó el reloj 11 minutos.")
                print("Reservas vencidas:", ", ".join(vencidas) if vencidas else "ninguna")
            elif opcion == "0":
                print("Hasta luego.")
                return
            else:
                print("Elige una opción del menú.")
        except (ReglaDeNegocio, ValueError) as exc:
            print(f"No se pudo completar: {exc}")
        print()


if __name__ == "__main__":
    main()
