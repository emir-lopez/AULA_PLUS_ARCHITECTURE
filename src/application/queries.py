"""CQRS básico (ADR-003): Queries con handlers que devuelven DTOs de lectura."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from domain.exceptions import RecursoNoEncontrado
from domain.policies import ParametrosOperacion
from domain.value_objects import VentanaHoraria

from .ports import LecturasAulaPlus, Reloj


@dataclass(frozen=True)
class ObtenerTutoresDisponiblesQuery:
    ventana: VentanaHoraria


@dataclass(frozen=True)
class ObtenerDetalleSesionQuery:
    sesion_id: str


class ConsultasAulaPlus:
    def __init__(self, lecturas: LecturasAulaPlus, reloj: Reloj, params: ParametrosOperacion | None = None):
        self.lecturas = lecturas
        self.reloj = reloj
        self.params = params or ParametrosOperacion()

    def tutores_disponibles(self, query: ObtenerTutoresDisponiblesQuery) -> list[dict]:
        """US-11: oculta perfiles sin agenda actualizada en 7 días y tutores suspendidos."""
        return self.lecturas.tutores_disponibles(query.ventana, self.reloj.ahora(), self.params.dias_vigencia_agenda)

    def detalle_sesion(self, query: ObtenerDetalleSesionQuery) -> dict:
        detalle = self.lecturas.detalle_sesion(query.sesion_id)
        if not detalle:
            raise RecursoNoEncontrado("SesionNoEncontrada", f"No existe la sesión {query.sesion_id}")
        return detalle

    def sesiones(self) -> list[dict]:
        return self.lecturas.sesiones()

    def tutores(self) -> list[dict]:
        """Catálogo con la agenda vigente: solo bloques que aún no terminan."""
        return self.lecturas.tutores(self.reloj.ahora())

    def sedes(self) -> list[dict]:
        return self.lecturas.sedes()

    def parametros(self) -> dict:
        """Plazos del BRD y hora del servidor, para que la interfaz calcule los mismos límites."""
        return {"ahora": self.reloj.ahora().isoformat(), **asdict(self.params)}

    def pagos_listos_para_liberar(self) -> list[str]:
        return self.lecturas.pagos_listos_para_liberar(self.reloj.ahora(), self.params.horas_retencion)

    def disputas_pendientes(self) -> list[dict]:
        return self.lecturas.disputas_pendientes()

    def eventos(self, agregado_id: str | None = None) -> list[dict]:
        return [
            {"nombre": e.nombre, "agregado_id": e.agregado_id, "ocurrido_en": e.ocurrido_en.isoformat(),
             "datos": e.datos}
            for e in self.lecturas.eventos(agregado_id)
        ]

    def indicadores(self) -> dict:
        """NB-15 / BRD sección 9: tasa de completadas vs. canceladas/disputadas, comisiones y reembolsos."""
        return self.lecturas.indicadores()
