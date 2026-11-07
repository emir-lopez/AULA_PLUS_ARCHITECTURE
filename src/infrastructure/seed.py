"""Datos ficticios de demostración (SEED_DEMO=true).

Idempotente: se ejecuta en cada arranque, crea lo que falte y completa los horarios de los
próximos ``dias`` sin duplicar. Así la demo siempre tiene bloques futuros y los tutores
siguen visibles (R-10: perfil actualizado en los últimos 7 días).
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from application.services import ServicioAgendaTutor
from domain.exceptions import ConflictoDeRecurso
from domain.sede import Sede
from domain.value_objects import Dinero, VentanaHoraria

TUTORES = [
    ("T-001", "Laura Méndez (Python)", "350.00"),
    ("T-002", "Carlos Ruiz (Bases de datos)", "420.00"),
    ("T-003", "Sofía Garza (Redes)", "300.00"),
]
SEDES = [Sede("SEDE-FIME", "Biblioteca FIME", cupo_maximo=2), Sede("SEDE-CENTRO", "Sala Centro", cupo_maximo=10)]
HORAS = (9, 11, 16, 18)


def bloques_demo(ahora: datetime, dias: int) -> list[tuple[str, VentanaHoraria]]:
    manana = (ahora + timedelta(days=1)).date()
    bloques = []
    for d in range(dias):
        dia = manana + timedelta(days=d)
        for hora in HORAS:
            inicio = datetime.combine(dia, time(hora), tzinfo=ahora.tzinfo)
            ventana = VentanaHoraria(inicio, inicio + timedelta(hours=1))
            bloques.append((f"B-{dia.strftime('%m%d')}-{hora:02d}", ventana))
    return bloques


def sembrar(servicio: ServicioAgendaTutor, ahora: datetime, dias: int = 14) -> int:
    for sede in SEDES:
        try:
            servicio.registrar_sede(sede)
        except ConflictoDeRecurso:
            pass
    agregados = 0
    for tutor_id, nombre, tarifa in TUTORES:
        try:
            servicio.registrar_tutor(tutor_id, nombre, Dinero(Decimal(tarifa)))
        except ConflictoDeRecurso:
            pass  # ya existía: solo se completan sus horarios
        agregados += servicio.publicar_disponibilidad(tutor_id, bloques_demo(ahora, dias))
    return agregados
