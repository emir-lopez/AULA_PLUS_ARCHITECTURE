"""Specification Pattern: reglas de negocio con nombre, combinables con & | ~.

Una Specification solo responde verdadero/falso sobre un candidato y nunca lo
modifica. ``verificar`` lanza ``ReglaDeNegocioViolada`` con el código de la
primera regla que falla, para que la API devuelva un motivo de negocio.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Generic, TypeVar

from .exceptions import ReglaDeNegocioViolada

T = TypeVar("T")


class Specification(ABC, Generic[T]):
    codigo: str = "ReglaNoCumplida"

    @abstractmethod
    def es_satisfecha_por(self, candidato: T) -> bool: ...

    def motivo_de_falla(self, candidato: T) -> str | None:
        return None if self.es_satisfecha_por(candidato) else self.codigo

    def verificar(self, candidato: T) -> None:
        motivo = self.motivo_de_falla(candidato)
        if motivo is not None:
            raise ReglaDeNegocioViolada(motivo)

    def __and__(self, otra: Specification[T]) -> Specification[T]:
        return _And(self, otra)

    def __or__(self, otra: Specification[T]) -> Specification[T]:
        return _Or(self, otra)

    def __invert__(self) -> Specification[T]:
        return _Not(self)


class _And(Specification[T]):
    def __init__(self, izq: Specification[T], der: Specification[T]):
        self.izq, self.der = izq, der

    def es_satisfecha_por(self, candidato: T) -> bool:
        return self.izq.es_satisfecha_por(candidato) and self.der.es_satisfecha_por(candidato)

    def motivo_de_falla(self, candidato: T) -> str | None:
        return self.izq.motivo_de_falla(candidato) or self.der.motivo_de_falla(candidato)


class _Or(Specification[T]):
    def __init__(self, izq: Specification[T], der: Specification[T]):
        self.izq, self.der = izq, der
        self.codigo = f"{izq.codigo}|{der.codigo}"

    def es_satisfecha_por(self, candidato: T) -> bool:
        return self.izq.es_satisfecha_por(candidato) or self.der.es_satisfecha_por(candidato)


class _Not(Specification[T]):
    def __init__(self, interna: Specification[T]):
        self.interna = interna
        self.codigo = f"No{interna.codigo}"

    def es_satisfecha_por(self, candidato: T) -> bool:
        return not self.interna.es_satisfecha_por(candidato)


class SpecificationSimple(Specification[T]):
    """Envuelve un predicado con nombre. Útil para reglas de una línea."""

    def __init__(self, codigo: str, predicado: Any):
        self.codigo = codigo
        self._predicado = predicado

    def es_satisfecha_por(self, candidato: T) -> bool:
        return bool(self._predicado(candidato))


# ---------------------------------------------------------------------------
# Reglas de reserva (CU-01): US-01, US-11, US-14, US-09
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SolicitudDeReserva:
    """Candidato que evalúan las Specifications de reserva."""

    inicio_sesion: datetime
    ahora: datetime
    agenda_actualizada_en: datetime
    tutor_suspendido: bool
    bloque_disponible: bool
    es_presencial: bool
    ocupacion_sede: int = 0
    cupo_sede: int = 0


class AnticipacionMinimaSpec(Specification[SolicitudDeReserva]):
    """R-02 / US-01: la sesión debe iniciar al menos 2 horas después de reservar."""

    codigo = "AnticipacionInsuficiente"

    def __init__(self, horas: int = 2):
        self.minimo = timedelta(hours=horas)

    def es_satisfecha_por(self, c: SolicitudDeReserva) -> bool:
        return c.inicio_sesion - c.ahora >= self.minimo


class PerfilVigenteSpec(Specification[SolicitudDeReserva]):
    """R-10 / US-11: perfil sin actualizar agenda en 7 días se oculta (BRD restr. 3)."""

    codigo = "PerfilNoVisible"

    def __init__(self, dias: int = 7):
        self.maximo = timedelta(days=dias)

    def es_satisfecha_por(self, c: SolicitudDeReserva) -> bool:
        return c.ahora - c.agenda_actualizada_en <= self.maximo


class TutorSuspendidoSpec(Specification[SolicitudDeReserva]):
    """US-09: un tutor suspendido por marcas de incumplimiento no recibe reservas."""

    codigo = "TutorSuspendido"

    def es_satisfecha_por(self, c: SolicitudDeReserva) -> bool:
        return c.tutor_suspendido


class BloqueDisponibleSpec(Specification[SolicitudDeReserva]):
    """NB-02 / US-03: solo se reserva un bloque Disponible y sin empalmes."""

    codigo = "HorarioNoDisponible"

    def es_satisfecha_por(self, c: SolicitudDeReserva) -> bool:
        return c.bloque_disponible


class EsPresencialSpec(Specification[SolicitudDeReserva]):
    codigo = "ModalidadNoPresencial"

    def es_satisfecha_por(self, c: SolicitudDeReserva) -> bool:
        return c.es_presencial


class CupoDisponibleSpec(Specification[SolicitudDeReserva]):
    """R-07 / US-14 / NB-10: no hay sobrecupo en la sede."""

    codigo = "SinCupoEnSede"

    def es_satisfecha_por(self, c: SolicitudDeReserva) -> bool:
        return c.ocupacion_sede < c.cupo_sede


def reserva_permitida(horas_anticipacion: int = 2, dias_vigencia: int = 7) -> Specification[SolicitudDeReserva]:
    """Composición AND / OR / NOT usada por TransaccionSesion.reservar.

    anticipación AND perfil vigente AND NOT suspendido AND bloque disponible
    AND (NOT presencial OR cupo disponible)
    """
    cupo_ok = ~EsPresencialSpec() | CupoDisponibleSpec()
    cupo_ok.codigo = CupoDisponibleSpec.codigo
    no_suspendido = ~TutorSuspendidoSpec()
    no_suspendido.codigo = TutorSuspendidoSpec.codigo
    return (
        AnticipacionMinimaSpec(horas_anticipacion)
        & PerfilVigenteSpec(dias_vigencia)
        & no_suspendido
        & BloqueDisponibleSpec()
        & cupo_ok
    )


# ---------------------------------------------------------------------------
# Reglas de liberación de fondos (CU-05): R-05, US-17, BRD restricción 6
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CandidatoLiberacion:
    sesion_completada: bool
    pago_confirmado: bool
    disputa_abierta: bool
    completada_en: datetime | None
    ahora: datetime


class SesionCompletadaSpec(Specification[CandidatoLiberacion]):
    codigo = "SesionNoCompletada"

    def es_satisfecha_por(self, c: CandidatoLiberacion) -> bool:
        return c.sesion_completada


class PagoConfirmadoSpec(Specification[CandidatoLiberacion]):
    codigo = "PagoNoConfirmado"

    def es_satisfecha_por(self, c: CandidatoLiberacion) -> bool:
        return c.pago_confirmado


class DisputaAbiertaSpec(Specification[CandidatoLiberacion]):
    codigo = "DisputaAbierta"

    def es_satisfecha_por(self, c: CandidatoLiberacion) -> bool:
        return c.disputa_abierta


class RetencionCumplidaSpec(Specification[CandidatoLiberacion]):
    """BRD restricción 6: no liberar antes de 48 h desde Completada (ADR-004, H-01)."""

    codigo = "RetencionVigente"

    def __init__(self, horas: int = 48):
        self.retencion = timedelta(hours=horas)

    def es_satisfecha_por(self, c: CandidatoLiberacion) -> bool:
        return c.completada_en is not None and c.ahora >= c.completada_en + self.retencion


def liberacion_permitida(horas_retencion: int = 48) -> Specification[CandidatoLiberacion]:
    """NOT disputa abierta AND completada AND pago confirmado AND retención cumplida."""
    sin_disputa = ~DisputaAbiertaSpec()
    sin_disputa.codigo = DisputaAbiertaSpec.codigo
    return (
        sin_disputa
        & SesionCompletadaSpec()
        & PagoConfirmadoSpec()
        & RetencionCumplidaSpec(horas_retencion)
    )
