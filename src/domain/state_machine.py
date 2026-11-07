"""Máquinas de estado explícitas de AulaPlus.

La tabla de transiciones es la única fuente de verdad: los Aggregates llaman a
``transicionar`` y cualquier combinación (estado, acción) ausente lanza
``TransicionInvalida`` (HTTP 409) sin modificar nada.

Ciclo de la sesión (BPMN U2 y glosario "Estados de sesión"):

    Reservada --confirmar_pago--> Confirmada --completar--> Completada
        |                            |   |  \\--enviar_a_revision--> EnRevision
        |--expirar--> Cancelada      |   |--registrar_no_show--> NoShow
                                     |--cancelar_por_estudiante / cancelar_por_tutor--> Cancelada
    Completada --abrir_disputa--> EnRevision
    EnRevision --resolver_a_favor_tutor--> Completada
    EnRevision --resolver_a_favor_estudiante--> Cancelada
"""
from __future__ import annotations

from enum import StrEnum

from .exceptions import TransicionInvalida


class EstadoSesion(StrEnum):
    RESERVADA = "Reservada"
    CONFIRMADA = "Confirmada"
    COMPLETADA = "Completada"
    EN_REVISION = "EnRevision"
    CANCELADA = "Cancelada"
    NO_SHOW = "NoShow"


class AccionSesion(StrEnum):
    CONFIRMAR_PAGO = "confirmar_pago"
    EXPIRAR = "expirar"
    CANCELAR_POR_ESTUDIANTE = "cancelar_por_estudiante"
    CANCELAR_POR_TUTOR = "cancelar_por_tutor"
    COMPLETAR = "completar"
    ENVIAR_A_REVISION = "enviar_a_revision"
    REGISTRAR_NO_SHOW = "registrar_no_show"
    ABRIR_DISPUTA = "abrir_disputa"
    RESOLVER_A_FAVOR_TUTOR = "resolver_a_favor_tutor"
    RESOLVER_A_FAVOR_ESTUDIANTE = "resolver_a_favor_estudiante"


TRANSICIONES_SESION: dict[tuple[EstadoSesion, AccionSesion], EstadoSesion] = {
    (EstadoSesion.RESERVADA, AccionSesion.CONFIRMAR_PAGO): EstadoSesion.CONFIRMADA,
    (EstadoSesion.RESERVADA, AccionSesion.EXPIRAR): EstadoSesion.CANCELADA,
    (EstadoSesion.CONFIRMADA, AccionSesion.CANCELAR_POR_ESTUDIANTE): EstadoSesion.CANCELADA,
    (EstadoSesion.CONFIRMADA, AccionSesion.CANCELAR_POR_TUTOR): EstadoSesion.CANCELADA,
    (EstadoSesion.CONFIRMADA, AccionSesion.COMPLETAR): EstadoSesion.COMPLETADA,
    (EstadoSesion.CONFIRMADA, AccionSesion.ENVIAR_A_REVISION): EstadoSesion.EN_REVISION,
    (EstadoSesion.CONFIRMADA, AccionSesion.REGISTRAR_NO_SHOW): EstadoSesion.NO_SHOW,
    (EstadoSesion.COMPLETADA, AccionSesion.ABRIR_DISPUTA): EstadoSesion.EN_REVISION,
    (EstadoSesion.EN_REVISION, AccionSesion.RESOLVER_A_FAVOR_TUTOR): EstadoSesion.COMPLETADA,
    (EstadoSesion.EN_REVISION, AccionSesion.RESOLVER_A_FAVOR_ESTUDIANTE): EstadoSesion.CANCELADA,
}

ESTADOS_FINALES = frozenset({EstadoSesion.CANCELADA, EstadoSesion.NO_SHOW})


def transicionar(estado: EstadoSesion, accion: AccionSesion) -> EstadoSesion:
    try:
        return TRANSICIONES_SESION[(estado, accion)]
    except KeyError:
        raise TransicionInvalida(
            "TransicionInvalida",
            f"No se puede '{accion.value}' una sesión en estado {estado.value}",
        ) from None


def acciones_permitidas(estado: EstadoSesion) -> list[AccionSesion]:
    return [accion for (origen, accion) in TRANSICIONES_SESION if origen == estado]


class EstadoPago(StrEnum):
    PENDIENTE = "Pendiente"
    CONFIRMADO = "Confirmado"
    LIBERADO = "Liberado"
    REEMBOLSADO = "Reembolsado"
    REEMBOLSO_PARCIAL = "ReembolsoParcial"


class EstadoBloque(StrEnum):
    DISPONIBLE = "Disponible"
    CONGELADO = "Congelado"
    BLOQUEADO = "Bloqueado"


TRANSICIONES_BLOQUE: dict[tuple[EstadoBloque, str], EstadoBloque] = {
    (EstadoBloque.DISPONIBLE, "congelar"): EstadoBloque.CONGELADO,
    (EstadoBloque.CONGELADO, "bloquear"): EstadoBloque.BLOQUEADO,
    (EstadoBloque.CONGELADO, "liberar"): EstadoBloque.DISPONIBLE,
    (EstadoBloque.BLOQUEADO, "liberar"): EstadoBloque.DISPONIBLE,
}


def transicionar_bloque(estado: EstadoBloque, accion: str) -> EstadoBloque:
    try:
        return TRANSICIONES_BLOQUE[(estado, accion)]
    except KeyError:
        raise TransicionInvalida(
            "HorarioNoDisponible", f"El bloque en estado {estado.value} no admite '{accion}'"
        ) from None
