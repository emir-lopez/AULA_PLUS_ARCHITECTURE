"""Datos ficticios de demostración (SEED_DEMO=true). Idempotente: no duplica si ya existen."""
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


def sembrar(servicio: ServicioAgendaTutor, ahora: datetime, dias: int = 5) -> int:
    creados = 0
    for sede in SEDES:
        try:
            servicio.registrar_sede(sede)
        except ConflictoDeRecurso:
            pass
    manana = (ahora + timedelta(days=1)).date()
    for tutor_id, nombre, tarifa in TUTORES:
        try:
            servicio.registrar_tutor(tutor_id, nombre, Dinero(Decimal(tarifa)))
        except ConflictoDeRecurso:
            continue  # ya sembrado
        for d in range(dias):
            for hora in (9, 11, 16, 18):
                inicio = datetime.combine(manana + timedelta(days=d), time(hora), tzinfo=ahora.tzinfo)
                bloque_id = f"B-{(manana + timedelta(days=d)).strftime('%m%d')}-{hora:02d}"
                servicio.agregar_bloque(tutor_id, bloque_id, VentanaHoraria(inicio, inicio + timedelta(hours=1)))
                creados += 1
    return creados
