"""Aggregate AgendaTutor: disponibilidad del tutor sin empalmes ni doble ocupación."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import events as ev
from .events import EventoDominio
from .exceptions import ConflictoDeRecurso, DatoInvalido, RecursoNoEncontrado
from .policies import PoliticaSuspension
from .state_machine import EstadoBloque, transicionar_bloque
from .value_objects import VentanaHoraria, exigir_zona_horaria


@dataclass
class BloqueDeAgenda:
    bloque_id: str
    ventana: VentanaHoraria
    estado: EstadoBloque = EstadoBloque.DISPONIBLE
    sesion_id: str | None = None


@dataclass
class AgendaTutor:
    """Raíz del calendario. Invariantes INV-AT-01 (sin empalmes) e INV-AT-02 (transiciones)."""

    tutor_id: str
    nombre: str
    tarifa_hora: str
    actualizada_en: datetime
    bloques: dict[str, BloqueDeAgenda] = field(default_factory=dict)
    marcas_incumplimiento: int = 0
    suspendido: bool = False
    version: int = 0
    eventos: list[EventoDominio] = field(default_factory=list)

    def __post_init__(self) -> None:
        exigir_zona_horaria(self.actualizada_en, "fecha de actualización")

    # -- disponibilidad -----------------------------------------------------
    def agregar_bloque(self, bloque_id: str, ventana: VentanaHoraria, ahora: datetime) -> BloqueDeAgenda:
        if bloque_id in self.bloques:
            raise ConflictoDeRecurso("BloqueDuplicado", f"El bloque {bloque_id} ya existe")
        if any(b.ventana.se_empalma(ventana) for b in self.bloques.values()):
            raise ConflictoDeRecurso("BloqueEmpalmado", "El bloque se empalma con otro del tutor")
        bloque = BloqueDeAgenda(bloque_id, ventana)
        self.bloques[bloque_id] = bloque
        self.actualizada_en = exigir_zona_horaria(ahora)
        return bloque

    def publicar_disponibilidad(self, bloques: list[tuple[str, VentanaHoraria]], ahora: datetime) -> int:
        """El tutor publica varios bloques a la vez; omite los que ya existen o se empalman (INV-AT-01).

        Publicar disponibilidad cuenta como actualizar la agenda (R-10), aunque todos los bloques ya existieran.
        """
        agregados = 0
        for bloque_id, ventana in bloques:
            if bloque_id in self.bloques or any(b.ventana.se_empalma(ventana) for b in self.bloques.values()):
                continue
            self.bloques[bloque_id] = BloqueDeAgenda(bloque_id, ventana)
            agregados += 1
        self.actualizada_en = exigir_zona_horaria(ahora)
        return agregados

    def bloque(self, bloque_id: str) -> BloqueDeAgenda:
        try:
            return self.bloques[bloque_id]
        except KeyError:
            raise RecursoNoEncontrado("BloqueNoEncontrado", f"No existe el bloque {bloque_id}") from None

    def bloque_esta_disponible(self, bloque_id: str) -> bool:
        return self.bloque(bloque_id).estado == EstadoBloque.DISPONIBLE

    def congelar_bloque(self, bloque_id: str, sesion_id: str, ahora: datetime) -> None:
        bloque = self.bloque(bloque_id)
        bloque.estado = transicionar_bloque(bloque.estado, "congelar")
        bloque.sesion_id = sesion_id
        self.eventos.append(EventoDominio(ev.HORARIO_CONGELADO, self.tutor_id, ahora,
                                          {"bloque_id": bloque_id, "sesion_id": sesion_id}))

    def bloquear_bloque(self, bloque_id: str, sesion_id: str, ahora: datetime) -> None:
        """R-04 / US-03: al confirmarse el pago el bloque pasa de Congelado a Bloqueado."""
        bloque = self.bloque(bloque_id)
        self._exigir_duenia(bloque, sesion_id)
        bloque.estado = transicionar_bloque(bloque.estado, "bloquear")
        self.eventos.append(EventoDominio(ev.HORARIO_BLOQUEADO, self.tutor_id, ahora,
                                          {"bloque_id": bloque_id, "sesion_id": sesion_id}))

    def liberar_bloque(self, bloque_id: str, sesion_id: str, ahora: datetime) -> None:
        bloque = self.bloque(bloque_id)
        self._exigir_duenia(bloque, sesion_id)
        bloque.estado = transicionar_bloque(bloque.estado, "liberar")
        bloque.sesion_id = None
        self.eventos.append(EventoDominio(ev.HORARIO_LIBERADO, self.tutor_id, ahora,
                                          {"bloque_id": bloque_id, "sesion_id": sesion_id}))

    def extender_bloque(self, bloque_id: str, sesion_id: str, nueva_ventana: VentanaHoraria) -> None:
        """US-12: la extensión no puede empalmarse con otro bloque del tutor (INV-AT-01)."""
        bloque = self.bloque(bloque_id)
        self._exigir_duenia(bloque, sesion_id)
        if any(b.bloque_id != bloque_id and b.ventana.se_empalma(nueva_ventana) for b in self.bloques.values()):
            raise ConflictoDeRecurso("ExtensionEmpalmada", "El tutor tiene otro horario inmediatamente después")
        bloque.ventana = nueva_ventana

    @staticmethod
    def _exigir_duenia(bloque: BloqueDeAgenda, sesion_id: str) -> None:
        # INV-AT-05: solo la sesión que congeló el bloque puede bloquearlo o liberarlo.
        if bloque.sesion_id != sesion_id:
            raise ConflictoDeRecurso("HorarioNoDisponible", "El bloque pertenece a otra sesión")

    # -- incumplimientos (US-09) -------------------------------------------
    def registrar_incumplimiento(self, motivo: str, ahora: datetime, politica: PoliticaSuspension) -> None:
        if not motivo.strip():
            raise DatoInvalido("MotivoRequerido", "El incumplimiento requiere motivo")
        self.marcas_incumplimiento += 1
        self.eventos.append(EventoDominio(ev.MARCA_INCUMPLIMIENTO_REGISTRADA, self.tutor_id, ahora,
                                          {"motivo": motivo, "marcas": self.marcas_incumplimiento}))
        if not self.suspendido and politica.debe_suspender(self.marcas_incumplimiento):
            self.suspendido = True
            self.eventos.append(EventoDominio(ev.TUTOR_SUSPENDIDO, self.tutor_id, ahora,
                                              {"marcas": self.marcas_incumplimiento}))

    def extraer_eventos(self) -> list[EventoDominio]:
        eventos, self.eventos = self.eventos, []
        return eventos
