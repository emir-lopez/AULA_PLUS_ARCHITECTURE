"""Dominio: dos raíces de agregado y reglas confirmadas en la Unidad 2.

El dominio no importa repositorios, frameworks ni bases de datos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Protocol


class ReglaDeNegocio(Exception):
    """Rechazo expresado en términos del negocio."""


class DecisionPendiente(ReglaDeNegocio):
    """Una fuente del caso no permite fijar todavía esta política."""


def _fecha_valida(valor: datetime) -> None:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError("Las fechas deben incluir zona horaria")


@dataclass(frozen=True)
class Dinero:
    monto: Decimal

    def __post_init__(self) -> None:
        valor = Decimal(str(self.monto)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if valor < 0:
            raise ValueError("El monto no puede ser negativo")
        object.__setattr__(self, "monto", valor)

    def comision(self) -> Dinero:
        # R-01: 20 % de comisión sobre una sesión completada.
        return Dinero(self.monto * Decimal("0.20"))

    def restar(self, otro: Dinero) -> Dinero:
        return Dinero(self.monto - otro.monto)


@dataclass(frozen=True)
class VentanaHoraria:
    inicio: datetime
    fin: datetime

    def __post_init__(self) -> None:
        _fecha_valida(self.inicio)
        _fecha_valida(self.fin)
        if self.fin <= self.inicio:
            raise ValueError("La ventana debe terminar después de iniciar")

    def se_empalma(self, otra: VentanaHoraria) -> bool:
        return self.inicio < otra.fin and otra.inicio < self.fin


class EstadoBloque(StrEnum):
    DISPONIBLE = "Disponible"
    CONGELADO = "Congelado"
    BLOQUEADO = "Bloqueado"


class EstadoSesion(StrEnum):
    RESERVADA = "Reservada"
    CONFIRMADA = "Confirmada"
    CANCELADA = "Cancelada"
    COMPLETADA = "Completada"
    EN_REVISION = "EnRevision"


class EstadoPago(StrEnum):
    PENDIENTE = "Pendiente"
    CONFIRMADO = "Confirmado"
    LIBERADO = "Liberado"
    REEMBOLSADO = "Reembolsado"


@dataclass(frozen=True)
class EventoDominio:
    nombre: str
    referencia_id: str


@dataclass
class BloqueDeAgenda:
    bloque_id: str
    ventana: VentanaHoraria
    estado: EstadoBloque = EstadoBloque.DISPONIBLE
    sesion_id: str | None = None


@dataclass
class AgendaTutor:
    tutor_id: str
    actualizada_en: datetime
    bloques: dict[str, BloqueDeAgenda]
    eventos: list[EventoDominio] = field(default_factory=list)

    def __post_init__(self) -> None:
        _fecha_valida(self.actualizada_en)

    def _bloque(self, bloque_id: str) -> BloqueDeAgenda:
        try:
            return self.bloques[bloque_id]
        except KeyError as exc:
            raise ReglaDeNegocio("HorarioNoDisponible") from exc

    def congelar_bloque(self, bloque_id: str, sesion_id: str, ahora: datetime) -> None:
        # R-10: un perfil sin agenda actualizada en siete días no ofrece horario.
        if ahora - self.actualizada_en > timedelta(days=7):
            raise ReglaDeNegocio("PerfilNoVisible")
        bloque = self._bloque(bloque_id)
        if bloque.estado != EstadoBloque.DISPONIBLE:
            raise ReglaDeNegocio("HorarioNoDisponible")
        if any(
            otro.bloque_id != bloque_id
            and otro.estado != EstadoBloque.DISPONIBLE
            and otro.ventana.se_empalma(bloque.ventana)
            for otro in self.bloques.values()
        ):
            raise ReglaDeNegocio("HorarioNoDisponible")
        bloque.estado = EstadoBloque.CONGELADO
        bloque.sesion_id = sesion_id
        self.eventos.append(EventoDominio("HorarioCongelado", bloque_id))

    def bloquear_bloque(self, bloque_id: str, sesion_id: str) -> None:
        bloque = self._bloque(bloque_id)
        if bloque.estado != EstadoBloque.CONGELADO or bloque.sesion_id != sesion_id:
            raise ReglaDeNegocio("HorarioNoDisponible")
        bloque.estado = EstadoBloque.BLOQUEADO
        self.eventos.append(EventoDominio("HorarioBloqueado", bloque_id))

    def liberar_bloque(self, bloque_id: str, sesion_id: str) -> None:
        bloque = self._bloque(bloque_id)
        if bloque.sesion_id != sesion_id or bloque.estado == EstadoBloque.DISPONIBLE:
            raise ReglaDeNegocio("HorarioNoDisponible")
        bloque.estado = EstadoBloque.DISPONIBLE
        bloque.sesion_id = None
        self.eventos.append(EventoDominio("HorarioLiberado", bloque_id))


class PoliticaReembolso(Protocol):
    def calcular(self, monto_pagado: Dinero, inicio: datetime, ahora: datetime) -> Dinero: ...


class PoliticaRetencion(Protocol):
    def permite_liberar(self, completada_en: datetime, ahora: datetime) -> bool: ...


@dataclass
class TransaccionSesion:
    sesion_id: str
    estudiante_id: str
    tutor_id: str
    bloque_id: str
    ventana: VentanaHoraria
    monto: Dinero
    congelado_hasta: datetime
    estado: EstadoSesion = EstadoSesion.RESERVADA
    estado_pago: EstadoPago = EstadoPago.PENDIENTE
    completada_en: datetime | None = None
    disputa_motivo: str | None = None
    monto_reembolso: Dinero | None = None
    eventos: list[EventoDominio] = field(default_factory=list)

    @classmethod
    def reservar(cls, sesion_id: str, estudiante_id: str, tutor_id: str,
                bloque_id: str, ventana: VentanaHoraria, monto: Dinero,
                ahora: datetime) -> TransaccionSesion:
        _fecha_valida(ahora)
        # R-02 y R-03: mínimo dos horas y congelamiento de diez minutos.
        if ventana.inicio - ahora < timedelta(hours=2):
            raise ReglaDeNegocio("AnticipacionInsuficiente")
        sesion = cls(sesion_id, estudiante_id, tutor_id, bloque_id, ventana,
                     monto, ahora + timedelta(minutes=10))
        sesion.eventos.append(EventoDominio("SesionReservada", sesion_id))
        return sesion

    def confirmar_pago(self, monto_pagado: Dinero, ahora: datetime) -> None:
        _fecha_valida(ahora)
        if self.estado != EstadoSesion.RESERVADA or ahora >= self.congelado_hasta:
            raise ReglaDeNegocio("CongelamientoVencido")
        if monto_pagado != self.monto:
            raise ReglaDeNegocio("MontoDePagoIncorrecto")
        self.estado = EstadoSesion.CONFIRMADA
        self.estado_pago = EstadoPago.CONFIRMADO
        self.eventos.append(EventoDominio("PagoConfirmado", self.sesion_id))

    def expirar_congelamiento(self, ahora: datetime) -> bool:
        _fecha_valida(ahora)
        if self.estado != EstadoSesion.RESERVADA or ahora < self.congelado_hasta:
            return False
        self.estado = EstadoSesion.CANCELADA
        self.eventos.append(EventoDominio("CongelamientoExpirado", self.sesion_id))
        return True

    def cancelar_por_estudiante(self, estudiante_id: str, ahora: datetime,
                                politica: PoliticaReembolso) -> Dinero:
        _fecha_valida(ahora)
        if estudiante_id != self.estudiante_id:
            raise ReglaDeNegocio("SolicitanteNoEsParteDeLaSesion")
        if self.estado != EstadoSesion.CONFIRMADA or ahora >= self.ventana.inicio:
            raise ReglaDeNegocio("SesionNoCancelable")
        reembolso = politica.calcular(self.monto, self.ventana.inicio, ahora)
        if reembolso.monto > self.monto.monto:
            raise ReglaDeNegocio("ReembolsoMayorAlPago")
        self.monto_reembolso = reembolso
        self.estado = EstadoSesion.CANCELADA
        self.estado_pago = EstadoPago.REEMBOLSADO if reembolso.monto else EstadoPago.CONFIRMADO
        self.eventos.append(EventoDominio("SesionCancelada", self.sesion_id))
        return reembolso

    def completar_con_evidencia(self, evidencia_validada: bool, ahora: datetime) -> None:
        # H-15: la captura y verificación de la evidencia se diseñará aparte.
        _fecha_valida(ahora)
        if self.estado != EstadoSesion.CONFIRMADA or not evidencia_validada:
            raise ReglaDeNegocio("SesionNoCompletada")
        self.estado = EstadoSesion.COMPLETADA
        self.completada_en = ahora
        self.eventos.append(EventoDominio("SesionCompletada", self.sesion_id))

    def abrir_disputa(self, solicitante_id: str, motivo: str) -> None:
        if solicitante_id not in (self.estudiante_id, self.tutor_id):
            raise ReglaDeNegocio("SolicitanteNoEsParteDeLaSesion")
        if self.disputa_motivo is not None:
            raise ReglaDeNegocio("DisputaYaAbierta")
        if self.estado != EstadoSesion.COMPLETADA:
            raise ReglaDeNegocio("SesionNoCompletada")
        if not motivo.strip():
            raise ReglaDeNegocio("MotivoRequerido")
        self.disputa_motivo = motivo.strip()
        self.estado = EstadoSesion.EN_REVISION
        self.eventos.append(EventoDominio("DisputaAbierta", self.sesion_id))

    def liberar_fondos(self, ahora: datetime, politica: PoliticaRetencion) -> tuple[Dinero, Dinero]:
        _fecha_valida(ahora)
        if self.estado == EstadoSesion.EN_REVISION or self.disputa_motivo:
            raise ReglaDeNegocio("DisputaAbierta")
        if self.estado != EstadoSesion.COMPLETADA or self.completada_en is None:
            raise ReglaDeNegocio("SesionNoCompletada")
        if self.estado_pago != EstadoPago.CONFIRMADO:
            raise ReglaDeNegocio("PagoNoConfirmado")
        # H-01: el plazo lo proporciona una política aprobada, no se fija aquí.
        if not politica.permite_liberar(self.completada_en, ahora):
            raise ReglaDeNegocio("RetencionVigente")
        comision = self.monto.comision()
        neto = self.monto.restar(comision)
        self.estado_pago = EstadoPago.LIBERADO
        self.eventos.append(EventoDominio("FondosLiberados", self.sesion_id))
        return comision, neto
