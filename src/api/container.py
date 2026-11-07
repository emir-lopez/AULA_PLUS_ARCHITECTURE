"""Composition Root: el único lugar que conoce las implementaciones concretas (DIP)."""
from __future__ import annotations

from dataclasses import dataclass

from application.ports import Reloj
from application.queries import ConsultasAulaPlus
from application.services import (
    Politicas,
    ServicioAgendaTutor,
    ServicioCancelacionSesion,
    ServicioDisputaSesion,
    ServicioEjecucionSesion,
    ServicioLiquidacionPago,
    ServicioReservaSesion,
)
from infrastructure.clock import RelojSistema
from infrastructure.config import Settings
from infrastructure.db import crear_engine, crear_esquema, crear_fabrica_sesiones
from infrastructure.lecturas import LecturasSql
from infrastructure.unit_of_work import FabricaUnidadDeTrabajoSql


@dataclass
class Contenedor:
    settings: Settings
    reloj: Reloj
    agenda: ServicioAgendaTutor
    reserva: ServicioReservaSesion
    cancelacion: ServicioCancelacionSesion
    ejecucion: ServicioEjecucionSesion
    disputa: ServicioDisputaSesion
    liquidacion: ServicioLiquidacionPago
    consultas: ConsultasAulaPlus


def construir_contenedor(settings: Settings, reloj: Reloj | None = None) -> Contenedor:
    engine = crear_engine(settings.url_normalizada)
    crear_esquema(engine)
    sesiones = crear_fabrica_sesiones(engine)
    uow = FabricaUnidadDeTrabajoSql(sesiones)
    reloj = reloj or RelojSistema()
    politicas = Politicas(params=settings.parametros(), suspension=settings.politica_suspension())
    return Contenedor(
        settings=settings, reloj=reloj,
        agenda=ServicioAgendaTutor(uow, reloj, politicas),
        reserva=ServicioReservaSesion(uow, reloj, politicas),
        cancelacion=ServicioCancelacionSesion(uow, reloj, politicas),
        ejecucion=ServicioEjecucionSesion(uow, reloj, politicas),
        disputa=ServicioDisputaSesion(uow, reloj, politicas),
        liquidacion=ServicioLiquidacionPago(uow, reloj, politicas),
        consultas=ConsultasAulaPlus(LecturasSql(sesiones), reloj, politicas.params),
    )
