"""Adaptador del paquete de datos del PIA (CSV del docente) al dominio de AulaPlus.

El paquete modela "inscripciones académicas" (PREINSCRITA -> VALIDADA -> INSCRITA ->
FINALIZADA | CANCELADA). Según su propia instrucción, NO reemplaza nuestros
requerimientos: se adaptan fixtures y oráculos y se documentan las diferencias
(docs/architecture/diferencias-paquete-pia.md).

Correspondencia usada:
  actor (estudiante)        -> Estudiante
  recurso (catálogo)        -> materia/tema con precio por hora; cantidad = horas
  operación                 -> solicitud de reserva (TransaccionSesion)
  autorizado                -> método de pago autorizado por la pasarela (BRD supuesto 1)
  PREINSCRITA               -> Reservada
  VALIDADA / INSCRITA       -> Confirmada (pago confirmado, horario bloqueado)
  FINALIZADA                -> Completada
  CANCELADA                 -> Cancelada
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from domain.exceptions import ErrorDeDominio, ReglaDeNegocioViolada
from domain.policies import ParametrosOperacion
from domain.sesion import TransaccionSesion
from domain.specifications import SolicitudDeReserva, Specification, SpecificationSimple
from domain.value_objects import Dinero, EvidenciaAsistencia, Modalidad, VentanaHoraria


@dataclass(frozen=True)
class Estudiante:
    actor_id: str
    nombre: str
    es_preferente: bool
    activo: bool


@dataclass(frozen=True)
class Recurso:
    recurso_id: str
    descripcion: str
    precio: Dinero
    capacidad: int
    habilitado: bool


@dataclass(frozen=True)
class Linea:
    recurso: Recurso
    cantidad: int

    @property
    def subtotal(self) -> Dinero:
        return self.recurso.precio.multiplicar(self.cantidad)


@dataclass
class Operacion:
    operacion_id: str
    estudiante: Estudiante
    estado_inicial: str
    fecha_solicitud: str
    promocion_activa: bool
    autorizado: bool
    lineas: list[Linea] = field(default_factory=list)

    @property
    def total(self) -> Dinero:
        total = Dinero.cero()
        for linea in self.lineas:
            total = total.sumar(linea.subtotal)
        return total


def _leer(ruta: Path) -> list[dict]:
    # utf-8-sig: los CSV del paquete traen BOM (Excel).
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def cargar_paquete(carpeta: Path) -> dict[str, Operacion]:
    actores = {r["actor_id"]: Estudiante(r["actor_id"], r["nombre"], r["es_preferente"] == "1", r["activo"] == "1")
               for r in _leer(carpeta / "actores.csv")}
    recursos = {r["recurso_id"]: Recurso(r["recurso_id"], r["descripcion"], Dinero(r["precio_mxn"]),
                                         int(r["capacidad_o_stock"]), r["habilitado"] == "1")
                for r in _leer(carpeta / "catalogo.csv")}
    operaciones = {
        r["operacion_id"]: Operacion(r["operacion_id"], actores[r["actor_id"]], r["estado_inicial"],
                                     r["fecha_solicitud"], r["promocion_activa"] == "1", r["autorizado"] == "1")
        for r in _leer(carpeta / "operaciones.csv")
    }
    for r in _leer(carpeta / "detalle_operaciones.csv"):
        cantidad = int(r["cantidad"])
        if cantidad <= 0:
            raise ReglaDeNegocioViolada("CantidadInvalida", f"{r['operacion_id']}: cantidad {cantidad}")
        operaciones[r["operacion_id"]].lineas.append(Linea(recursos[r["recurso_id"]], cantidad))
    return operaciones


# ------------------------------------------------------------ Specifications
EstudianteActivo: Specification[Operacion] = SpecificationSimple("EstudianteInactivo", lambda o: o.estudiante.activo)
TieneLineas: Specification[Operacion] = SpecificationSimple("OperacionSinLineas", lambda o: len(o.lineas) > 0)
PagoAutorizado: Specification[Operacion] = SpecificationSimple("PagoNoAutorizado", lambda o: o.autorizado)
RecursosHabilitados: Specification[Operacion] = SpecificationSimple(
    "RecursoDeshabilitado", lambda o: all(linea.recurso.habilitado for linea in o.lineas))
EstudiantePreferente: Specification[Operacion] = SpecificationSimple(
    "NoPreferente", lambda o: o.estudiante.es_preferente)
PromocionActiva: Specification[Operacion] = SpecificationSimple("PromocionActiva", lambda o: o.promocion_activa)


class TotalMinimoSpec(Specification[Operacion]):
    codigo = "TotalInsuficiente"

    def __init__(self, minimo: str = "1500"):
        self.minimo = Dinero(minimo)

    def es_satisfecha_por(self, o: Operacion) -> bool:
        return o.total.monto >= self.minimo.monto


# Regla 1 del paquete: actor activo AND al menos una línea AND autorización.
PUEDE_PROCESARSE = EstudianteActivo & TieneLineas & PagoAutorizado
# Regla 2 del paquete: preferente AND total >= 1500 AND NOT promoción activa.
# No existe en el BRD (programas de lealtad están fuera de alcance): solo se evalúa como oráculo del paquete.
BENEFICIO_REFERENCIA = EstudiantePreferente & TotalMinimoSpec("1500") & ~PromocionActiva


@dataclass(frozen=True)
class ResultadoCaso:
    caso_id: str
    operacion_id: str
    resultado: str
    evidencia: str


def ejecutar_casos(carpeta: Path) -> list[ResultadoCaso]:
    operaciones = cargar_paquete(carpeta)
    resultados = []
    for caso in _leer(carpeta / "casos_prueba.csv"):
        op = operaciones[caso["operacion_id"]]
        if caso["tipo_prueba"] == "validar_operacion":
            motivo = PUEDE_PROCESARSE.motivo_de_falla(op)
            resultados.append(ResultadoCaso(caso["caso_id"], op.operacion_id,
                                            "APROBADA" if motivo is None else "RECHAZADA",
                                            f"total={op.total.monto}; motivo={motivo or '-'}"))
        else:
            aplica = BENEFICIO_REFERENCIA.es_satisfecha_por(op)
            resultados.append(ResultadoCaso(caso["caso_id"], op.operacion_id,
                                            "APLICA" if aplica else "NO_APLICA",
                                            f"preferente={op.estudiante.es_preferente}; total={op.total.monto}; "
                                            f"promo={op.promocion_activa}"))
    return resultados


ESTADO_PAQUETE = {"Reservada": "PREINSCRITA", "Confirmada": "INSCRITA", "Completada": "FINALIZADA",
                  "Cancelada": "CANCELADA", "EnRevision": "EN_REVISION", "NoShow": "NO_SHOW"}


def _sesion_desde(op: Operacion, ahora: datetime) -> TransaccionSesion:
    horas = sum(linea.cantidad for linea in op.lineas) or 1
    inicio = ahora + timedelta(days=1)
    ventana = VentanaHoraria(inicio, inicio + timedelta(hours=horas))
    solicitud = SolicitudDeReserva(inicio, ahora, ahora, False, True, False)
    return TransaccionSesion.reservar(
        sesion_id=op.operacion_id, estudiante_id=op.estudiante.actor_id, tutor_id="T-PAQUETE",
        bloque_id=f"B-{op.operacion_id}", ventana=ventana, modalidad=Modalidad.EN_LINEA,
        monto=op.total if op.total.monto > 0 else Dinero("1"), solicitud=solicitud, params=ParametrosOperacion(),
    )


def ejecutar_transiciones(carpeta: Path, ahora: datetime | None = None) -> list[ResultadoCaso]:
    """Ejecuta transiciones_prueba.csv a través del Aggregate (nunca cambiando el estado a mano)."""
    ahora = ahora or datetime(2026, 11, 1, 12, tzinfo=UTC)
    operaciones = cargar_paquete(carpeta)
    evidencia_ok = EvidenciaAsistencia(ahora, ahora, False, True, True)
    resultados = []
    for caso in _leer(carpeta / "transiciones_prueba.csv"):
        op = operaciones[caso["operacion_id"]]
        accion = caso["accion_sugerida"]
        try:
            PUEDE_PROCESARSE.verificar(op)
            sesion = _sesion_desde(op, ahora)
            if accion == "aprobar":
                sesion.confirmar_pago(sesion.monto, ahora)
            elif accion == "repetir_aprobacion":
                sesion.confirmar_pago(sesion.monto, ahora)
                sesion.confirmar_pago(sesion.monto, ahora)
            elif accion == "completar":
                sesion.confirmar_pago(sesion.monto, ahora)
                sesion.completar_con_evidencia(evidencia_ok, sesion.ventana.fin)
            elif accion == "cancelar":
                sesion.expirar_congelamiento(ahora + timedelta(minutes=11))
            elif accion == "saltar_estado":
                sesion.completar_con_evidencia(evidencia_ok, sesion.ventana.fin)
            else:  # pragma: no cover - el paquete solo trae las cinco acciones anteriores
                raise ReglaDeNegocioViolada("AccionDesconocida", accion)
            eventos = ",".join(e.nombre for e in sesion.eventos)
            resultados.append(ResultadoCaso(caso["caso_id"], op.operacion_id, ESTADO_PAQUETE[sesion.estado.value],
                                            f"estado={sesion.estado.value}; eventos={eventos}"))
        except ErrorDeDominio as exc:
            resultados.append(ResultadoCaso(caso["caso_id"], op.operacion_id, f"EXCEPCION:{type(exc).__name__}",
                                            f"codigo={exc.codigo}; estado_final=PREINSCRITA"))
    return resultados


def escribir_resultados(ruta: Path, resultados: list[ResultadoCaso]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["caso_id", "operacion_id", "resultado_alumno", "evidencia"])
        for r in resultados:
            w.writerow([r.caso_id, r.operacion_id, r.resultado, r.evidencia])
