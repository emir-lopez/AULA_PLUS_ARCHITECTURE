"""Sede presencial: dato de referencia con capacidad máxima (NB-10, H-06)."""
from __future__ import annotations

from dataclasses import dataclass

from .exceptions import DatoInvalido


@dataclass(frozen=True)
class Sede:
    sede_id: str
    nombre: str
    cupo_maximo: int
    radio_geocerca_m: int = 200

    def __post_init__(self) -> None:
        if self.cupo_maximo <= 0:
            raise DatoInvalido("CupoInvalido", "El cupo máximo de la sede debe ser mayor a 0")
