"""Excepciones del dominio expresadas en lenguaje del negocio.

Cada excepción tiene un ``codigo`` estable (lo usa la API y las pruebas) y un
mensaje legible. La capa API traduce la jerarquía a códigos HTTP:

* DatoInvalido               -> 400
* RecursoNoEncontrado        -> 404
* TransicionInvalida         -> 409
* ConflictoDeRecurso         -> 409
* ReglaDeNegocioViolada      -> 422
"""
from __future__ import annotations


class ErrorDeDominio(Exception):
    codigo: str = "ErrorDeDominio"

    def __init__(self, codigo: str | None = None, mensaje: str | None = None):
        if codigo:
            self.codigo = codigo
        self.mensaje = mensaje or self.codigo
        super().__init__(f"{self.codigo}: {self.mensaje}")


class DatoInvalido(ErrorDeDominio, ValueError):
    """Un Value Object recibió un valor que nunca es válido (monto negativo, fecha sin zona...)."""

    codigo = "DatoInvalido"


class ReglaDeNegocioViolada(ErrorDeDominio):
    """La operación es comprensible pero una regla del BRD la impide."""

    codigo = "ReglaDeNegocioViolada"


class TransicionInvalida(ErrorDeDominio):
    """La máquina de estados no permite la acción desde el estado actual."""

    codigo = "TransicionInvalida"


class ConflictoDeRecurso(ErrorDeDominio):
    """Otro proceso ocupó el recurso (horario, cupo, versión del Aggregate)."""

    codigo = "ConflictoDeRecurso"


class RecursoNoEncontrado(ErrorDeDominio):
    codigo = "RecursoNoEncontrado"
