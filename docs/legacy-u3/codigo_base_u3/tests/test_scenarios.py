"""Escenarios elegidos para verificar reglas y límite transaccional."""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from aulaplus.cqrs import (
    ObtenerDetalleSesionQuery, ObtenerDetalleSesionQueryHandler,
    ObtenerTutoresDisponiblesQuery, ObtenerTutoresDisponiblesQueryHandler,
)
from aulaplus.domain import (
    AgendaTutor, BloqueDeAgenda, Dinero, EstadoBloque, EstadoSesion,
    ReglaDeNegocio, VentanaHoraria,
)
from aulaplus.memory import AlmacenMemoria, LecturasMemoria, RelojFijo
from aulaplus.services import ServicioDisputaSesion, ServicioLiquidacionPago, ServicioReservaSesion, SolicitudReserva


class PoliticaRetencionDePrueba:
    def permite_liberar(self, completada_en, ahora):
        return ahora >= completada_en + timedelta(hours=48)


class EscenariosAulaPlus(unittest.TestCase):
    def setUp(self):
        self.ahora = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
        self.reloj = RelojFijo(self.ahora)
        self.almacen = AlmacenMemoria()
        self.ventana = VentanaHoraria(self.ahora + timedelta(days=1),
                                      self.ahora + timedelta(days=1, hours=1))
        self.almacen.agendas["T-1"] = AgendaTutor(
            "T-1", self.ahora, {"B-1": BloqueDeAgenda("B-1", self.ventana)}
        )
        self.servicio = ServicioReservaSesion(self.almacen.unidad_de_trabajo, self.reloj)
        self.solicitud = SolicitudReserva("S-1", "E-1", "T-1", "B-1", Dinero(Decimal("500")))

    def test_reserva_congela_y_pago_bloquea_en_una_operacion(self):
        resultado = self.servicio.reservar_sesion(self.solicitud)
        self.assertEqual(resultado.estado, "Reservada")
        self.assertEqual(self.almacen.agendas["T-1"].bloques["B-1"].estado, EstadoBloque.CONGELADO)
        self.assertEqual(self.servicio.confirmar_pago_reserva("S-1", Dinero(500)), "Confirmada")
        self.assertEqual(self.almacen.agendas["T-1"].bloques["B-1"].estado, EstadoBloque.BLOQUEADO)
        self.assertEqual(self.almacen.transacciones["S-1"].estado, EstadoSesion.CONFIRMADA)
        detalle = ObtenerDetalleSesionQueryHandler(LecturasMemoria(self.almacen)).ejecutar(
            ObtenerDetalleSesionQuery("S-1", "E-1")
        )
        self.assertEqual((detalle.estado, detalle.estado_pago), ("Confirmada", "Confirmado"))

    def test_rechazo_por_menos_de_dos_horas_no_modifica_agenda(self):
        self.almacen.agendas["T-1"].bloques["B-1"].ventana = VentanaHoraria(
            self.ahora + timedelta(minutes=90), self.ahora + timedelta(minutes=150)
        )
        with self.assertRaisesRegex(ReglaDeNegocio, "AnticipacionInsuficiente"):
            self.servicio.reservar_sesion(self.solicitud)
        self.assertEqual(self.almacen.agendas["T-1"].bloques["B-1"].estado, EstadoBloque.DISPONIBLE)
        self.assertNotIn("S-1", self.almacen.transacciones)

    def test_segunda_reserva_del_mismo_bloque_se_rechaza(self):
        self.servicio.reservar_sesion(self.solicitud)
        segunda = SolicitudReserva("S-2", "E-2", "T-1", "B-1", Dinero(500))
        with self.assertRaisesRegex(ReglaDeNegocio, "HorarioNoDisponible"):
            self.servicio.reservar_sesion(segunda)
        self.assertEqual(set(self.almacen.transacciones), {"S-1"})

    def test_vencimiento_libera_y_el_pago_tardio_no_cambia_estado(self):
        self.servicio.reservar_sesion(self.solicitud)
        self.reloj.momento += timedelta(minutes=10)
        self.assertTrue(self.servicio.expirar_congelamiento("S-1"))
        self.assertFalse(self.servicio.expirar_congelamiento("S-1"))
        with self.assertRaisesRegex(ReglaDeNegocio, "CongelamientoVencido"):
            self.servicio.confirmar_pago_reserva("S-1", Dinero(500))
        self.assertEqual(self.almacen.agendas["T-1"].bloques["B-1"].estado, EstadoBloque.DISPONIBLE)
        self.assertEqual(self.almacen.transacciones["S-1"].estado, EstadoSesion.CANCELADA)

    def test_lectura_de_disponibilidad_no_muta_agregados(self):
        consulta = ObtenerTutoresDisponiblesQueryHandler(LecturasMemoria(self.almacen), self.reloj)
        disponibles = consulta.ejecutar(ObtenerTutoresDisponiblesQuery(self.ventana))
        self.assertEqual([(x.tutor_id, x.bloque_id) for x in disponibles], [("T-1", "B-1")])
        ventana_mas_larga = VentanaHoraria(self.ventana.inicio, self.ventana.fin + timedelta(minutes=30))
        self.assertEqual(consulta.ejecutar(ObtenerTutoresDisponiblesQuery(ventana_mas_larga)), [])
        self.servicio.reservar_sesion(self.solicitud)
        self.assertEqual(consulta.ejecutar(ObtenerTutoresDisponiblesQuery(self.ventana)), [])

    def test_disputa_impide_liberacion_aunque_politica_de_prueba_permita(self):
        self.servicio.reservar_sesion(self.solicitud)
        self.servicio.confirmar_pago_reserva("S-1", Dinero(500))
        # H-15: esta transición se prepara como fixture; falta el servicio de
        # evidencia y cierre de sesión para la implementación real.
        with self.almacen.unidad_de_trabajo() as uow:
            sesion = uow.transacciones.obtener("S-1")
            sesion.completar_con_evidencia(True, self.ventana.fin)
            uow.transacciones.guardar(sesion)
            uow.confirmar()
        self.assertEqual(
            ServicioDisputaSesion(self.almacen.unidad_de_trabajo).abrir_disputa("S-1", "E-1", "No asistió"),
            "EnRevision",
        )
        self.reloj.momento = self.ventana.fin + timedelta(hours=49)
        liquidacion = ServicioLiquidacionPago(
            self.almacen.unidad_de_trabajo, self.reloj, PoliticaRetencionDePrueba()
        )
        with self.assertRaisesRegex(ReglaDeNegocio, "DisputaAbierta"):
            liquidacion.liberar_pago_al_tutor("S-1")
        self.assertEqual(self.almacen.transacciones["S-1"].estado_pago.value, "Confirmado")


if __name__ == "__main__":
    unittest.main()
