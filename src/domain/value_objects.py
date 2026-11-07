"""Value Objects de AulaPlus: inmutables, comparados por valor y autovalidados."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum

from .exceptions import DatoInvalido

CENTAVO = Decimal("0.01")


def exigir_zona_horaria(valor: datetime, campo: str = "fecha") -> datetime:
    if not isinstance(valor, datetime) or valor.tzinfo is None or valor.utcoffset() is None:
        raise DatoInvalido("FechaSinZonaHoraria", f"La {campo} debe incluir zona horaria (UTC)")
    return valor


@dataclass(frozen=True)
class Dinero:
    """Monto en MXN con dos decimales. Nunca negativo. Usa Decimal, no float."""

    monto: Decimal
    moneda: str = "MXN"

    def __post_init__(self) -> None:
        if isinstance(self.monto, float):
            # Evita heredar la imprecisión binaria: 0.1 + 0.2 != 0.3
            valor_texto = repr(self.monto)
        else:
            valor_texto = str(self.monto)
        try:
            valor = Decimal(valor_texto).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError) as exc:
            raise DatoInvalido("MontoInvalido", f"Monto no numérico: {self.monto!r}") from exc
        if not valor.is_finite():
            raise DatoInvalido("MontoInvalido", "El monto debe ser finito")
        if valor < 0:
            raise DatoInvalido("MontoNegativo", f"El monto no puede ser negativo (recibido {valor})")
        if self.moneda != "MXN":
            raise DatoInvalido("MonedaNoSoportada", "AulaPlus opera solo en MXN (BRD 5.2)")
        object.__setattr__(self, "monto", valor)

    @classmethod
    def cero(cls) -> Dinero:
        return cls(Decimal("0"))

    @classmethod
    def desde_centavos(cls, centavos: int) -> Dinero:
        return cls(Decimal(centavos) / 100)

    @property
    def centavos(self) -> int:
        return int(self.monto * 100)

    def sumar(self, otro: Dinero) -> Dinero:
        return Dinero(self.monto + otro.monto)

    def restar(self, otro: Dinero) -> Dinero:
        return Dinero(self.monto - otro.monto)

    def por_porcentaje(self, porcentaje: Decimal) -> Dinero:
        return Dinero(self.monto * porcentaje)

    def multiplicar(self, cantidad: int) -> Dinero:
        if not isinstance(cantidad, int) or cantidad <= 0:
            raise DatoInvalido("CantidadInvalida", "La cantidad debe ser un entero mayor a 0")
        return Dinero(self.monto * cantidad)

    def __str__(self) -> str:
        return f"{self.monto} {self.moneda}"


@dataclass(frozen=True)
class PorcentajeComision:
    """R-01: AulaPlus retiene 20 % de cada sesión (BRD restricción 7)."""

    valor: Decimal = Decimal("0.20")

    def __post_init__(self) -> None:
        valor = Decimal(str(self.valor))
        if not Decimal("0") <= valor <= Decimal("1"):
            raise DatoInvalido("PorcentajeInvalido", "El porcentaje debe estar entre 0 y 1")
        object.__setattr__(self, "valor", valor)


@dataclass(frozen=True)
class DesgloseFinanciero:
    """Bruto = comisión + neto del tutor. Se calcula una vez al completar la sesión (US-19)."""

    bruto: Dinero
    comision: Dinero
    neto_tutor: Dinero
    porcentaje: PorcentajeComision

    @classmethod
    def calcular(cls, bruto: Dinero, porcentaje: PorcentajeComision | None = None) -> DesgloseFinanciero:
        porcentaje = porcentaje or PorcentajeComision()
        comision = bruto.por_porcentaje(porcentaje.valor)
        # El neto se obtiene por diferencia: comisión + neto == bruto siempre, sin perder centavos.
        return cls(bruto, comision, bruto.restar(comision), porcentaje)


@dataclass(frozen=True)
class VentanaHoraria:
    inicio: datetime
    fin: datetime

    def __post_init__(self) -> None:
        exigir_zona_horaria(self.inicio, "fecha de inicio")
        exigir_zona_horaria(self.fin, "fecha de fin")
        if self.fin <= self.inicio:
            raise DatoInvalido("VentanaInvalida", "La ventana debe terminar después de iniciar")

    @property
    def duracion(self) -> timedelta:
        return self.fin - self.inicio

    def se_empalma(self, otra: VentanaHoraria) -> bool:
        return self.inicio < otra.fin and otra.inicio < self.fin

    def contiene(self, otra: VentanaHoraria) -> bool:
        return self.inicio <= otra.inicio and otra.fin <= self.fin


class Modalidad(StrEnum):
    EN_LINEA = "EnLinea"
    PRESENCIAL = "Presencial"


class ParteSesion(StrEnum):
    ESTUDIANTE = "Estudiante"
    TUTOR = "Tutor"


@dataclass(frozen=True)
class EvidenciaAsistencia:
    """Evidencia verificable de que la sesión ocurrió (NB-01, US-04, US-05, US-06).

    * En línea: timestamp de conexión de tutor y estudiante.
    * Presencial: check-in del estudiante dentro de la geocerca de la sede.
    * Ambas modalidades: confirmación mutua al cierre.
    """

    conexion_tutor: datetime | None = None
    conexion_estudiante: datetime | None = None
    checkin_dentro_de_geocerca: bool = False
    confirma_estudiante: bool = False
    confirma_tutor: bool = False

    def es_suficiente(self, modalidad: Modalidad) -> bool:
        if modalidad == Modalidad.EN_LINEA:
            asistencia = self.conexion_tutor is not None and self.conexion_estudiante is not None
        else:
            asistencia = self.checkin_dentro_de_geocerca
        return asistencia and self.confirma_estudiante and self.confirma_tutor


@dataclass(frozen=True)
class Calificacion:
    puntos: int
    comentario: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.puntos, int) or not 1 <= self.puntos <= 5:
            raise DatoInvalido("CalificacionInvalida", "La calificación debe ser un entero de 1 a 5")
