"""Domain Services / políticas: reglas que no pertenecen a una sola entidad."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from .value_objects import Dinero, exigir_zona_horaria


@dataclass(frozen=True)
class CalculadoraReembolso:
    """R-06 / US-07 / NB-03: reembolso al estudiante según la anticipación.

    Política validada con el stakeholder (entrevista U2, hallazgo H-05 cerrado en ADR-004):
      * más de 24 h antes del inicio  -> 100 %
      * de 6 h a 24 h (ambos incluidos) -> 50 %
      * menos de 6 h                   -> 0 %
    """

    horas_reembolso_total: int = 24
    horas_reembolso_parcial: int = 6
    porcentaje_parcial: Decimal = Decimal("0.50")

    def porcentaje(self, inicio: datetime, ahora: datetime) -> Decimal:
        exigir_zona_horaria(inicio)
        exigir_zona_horaria(ahora)
        anticipacion = inicio - ahora
        if anticipacion > timedelta(hours=self.horas_reembolso_total):
            return Decimal("1")
        if anticipacion >= timedelta(hours=self.horas_reembolso_parcial):
            return self.porcentaje_parcial
        return Decimal("0")

    def calcular(self, monto_pagado: Dinero, inicio: datetime, ahora: datetime) -> Dinero:
        return monto_pagado.por_porcentaje(self.porcentaje(inicio, ahora))


@dataclass(frozen=True)
class PoliticaCompensacion:
    """R-13 / US-08 / NB-04: si el tutor cancela o no se presenta, el estudiante recupera el 100 %."""

    def calcular(self, monto_pagado: Dinero) -> Dinero:
        return monto_pagado


@dataclass(frozen=True)
class PoliticaSuspension:
    """R-14 / US-09: al acumular N marcas de incumplimiento el tutor se suspende.

    El umbral es un parámetro de negocio (H-07). Valor de trabajo: 3, configurable
    con la variable de entorno MARCAS_PARA_SUSPENSION.
    """

    umbral_marcas: int = 3

    def debe_suspender(self, marcas: int) -> bool:
        return marcas >= self.umbral_marcas


@dataclass(frozen=True)
class ParametrosOperacion:
    """Plazos confirmados en el BRD (restricciones 6, 8, 9, 10 y 11)."""

    minutos_congelamiento: int = 10
    horas_retencion: int = 48
    horas_mediacion: int = 72
    minutos_tolerancia_no_show: int = 10
    horas_anticipacion_minima: int = 2
    dias_vigencia_agenda: int = 7
    minutos_tolerancia_conexion: int = 15
    minutos_maximos_extension: int = 60
