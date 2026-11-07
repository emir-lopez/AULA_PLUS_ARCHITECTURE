"""DTOs de entrada/salida de la API (Pydantic). Solo forma de los datos; las reglas están en el dominio."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects import Modalidad, ParteSesion


class TutorIn(BaseModel):
    tutor_id: str = Field(min_length=1, max_length=40, examples=["T-100"])
    nombre: str = Field(min_length=1, max_length=120, examples=["Ana López (Cálculo)"])
    tarifa_hora: Decimal = Field(gt=0, examples=["350.00"])


class BloqueIn(BaseModel):
    bloque_id: str = Field(min_length=1, max_length=40, examples=["B-1"])
    inicio: datetime = Field(examples=["2026-11-20T16:00:00Z"])
    fin: datetime = Field(examples=["2026-11-20T17:00:00Z"])


class SedeIn(BaseModel):
    sede_id: str = Field(min_length=1, max_length=40)
    nombre: str = Field(min_length=1, max_length=120)
    cupo_maximo: int = Field(gt=0)


class ReservaIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "sesion_id": "S-001", "estudiante_id": "E-001", "tutor_id": "T-001",
        "bloque_id": "B-1121-16", "modalidad": "EnLinea"}})

    sesion_id: str = Field(min_length=1, max_length=40)
    estudiante_id: str = Field(min_length=1, max_length=40)
    tutor_id: str = Field(min_length=1, max_length=40)
    bloque_id: str = Field(min_length=1, max_length=40)
    modalidad: Modalidad = Modalidad.EN_LINEA
    sede_id: str | None = None


class PagoIn(BaseModel):
    monto: Decimal = Field(examples=["350.00"])
    resultado: str = Field("Confirmado", pattern="^(Confirmado|Fallido)$",
                           description="Resultado devuelto por la pasarela de pago")
    motivo: str | None = Field(None, description="Motivo del rechazo cuando resultado=Fallido")


class SolicitanteIn(BaseModel):
    solicitante_id: str = Field(min_length=1, max_length=40)


class EvidenciaIn(BaseModel):
    conexion_tutor: datetime | None = None
    conexion_estudiante: datetime | None = None
    checkin_dentro_de_geocerca: bool = False
    confirma_estudiante: bool = False
    confirma_tutor: bool = False


class NoShowIn(BaseModel):
    parte_ausente: ParteSesion


class CalificacionIn(BaseModel):
    estudiante_id: str
    puntos: int = Field(ge=1, le=5)
    comentario: str = Field("", max_length=500)


class DisputaIn(BaseModel):
    solicitante_id: str = Field(min_length=1, max_length=40)
    motivo: str = Field(min_length=1, max_length=500)


class ResolucionIn(BaseModel):
    a_favor_de: ParteSesion
    resolucion: str = Field(min_length=1, max_length=500)


class ErrorOut(BaseModel):
    codigo: str
    mensaje: str
