# Diferencias entre el paquete de datos del PIA y los requisitos de AulaPlus

El paquete del docente (`tests/data/paquete_pia/`, 40 actores, 20 recursos, 60 operaciones, 117 líneas,
120 casos y 20 transiciones) describe un giro de **inscripciones académicas**. Su propio texto indica:

> "El PIA oficial exige que la implementación se derive del BRD […] elaborados por el equipo. Si difieren, documentar
> las diferencias y adaptar fixtures y oráculos; no reemplazar los requerimientos propios con estas reglas."

Por eso el dominio de AulaPlus **no cambió**: se escribió un adaptador (`src/infrastructure/paquete_pia.py`) que
importa los CSV y los ejecuta sobre `TransaccionSesion`.

## Correspondencia de conceptos

| Paquete | AulaPlus | Comentario |
|---|---|---|
| Actor (estudiante) | Estudiante | `activo` y `es_preferente` se conservan |
| Recurso / catálogo (curso) | Materia con tarifa por hora | `precio_mxn × cantidad` = monto de la sesión (cantidad = horas) |
| `capacidad_o_stock` | Cupo de sede | Solo informativo en el paquete |
| Operación | Solicitud de reserva | Se crea una `TransaccionSesion` en línea, 1 día en el futuro |
| `autorizado` | Pago autorizado por la pasarela | BRD supuesto 1 |
| `promocion_activa` | — | AulaPlus no tiene promociones (lealtad fuera de alcance) |

## Estados

| Paquete | AulaPlus | Acción que lo produce |
|---|---|---|
| PREINSCRITA | Reservada | `TransaccionSesion.reservar` |
| VALIDADA → INSCRITA | Confirmada | `confirmar_pago` (AulaPlus no distingue validar de inscribir: el pago confirma y bloquea) |
| FINALIZADA | Completada | `completar_con_evidencia` |
| CANCELADA | Cancelada | `expirar_congelamiento` (cancelación antes de pagar) |
| — | EnRevision, NoShow | Estados propios de AulaPlus sin equivalente |

## Acciones de `transiciones_prueba.csv`

| Acción | Ejecución en AulaPlus | Resultado esperado |
|---|---|---|
| `aprobar` | `confirmar_pago` | INSCRITA (Confirmada) + `PagoConfirmado`, `SesionConfirmada` |
| `completar` | `confirmar_pago` → `completar_con_evidencia` | FINALIZADA (Completada) + `SesionCompletada` |
| `cancelar` | `expirar_congelamiento` | CANCELADA + `CongelamientoExpirado`, `SesionCancelada` |
| `repetir_aprobacion` | `confirmar_pago` dos veces | `TransicionInvalida` en la segunda (409) |
| `saltar_estado` | `completar` desde Reservada | `TransicionInvalida` (409) |

Antes de cualquier acción se evalúa `PUEDE_PROCESARSE`; si falla, se registra la excepción y el estado queda en
PREINSCRITA (por ejemplo, AUL-S008/AUL-S016 sin autorización y AUL-S013 sin líneas).

## Reglas del paquete

| Regla del paquete | Tratamiento |
|---|---|
| `puede_procesarse` = activo AND ≥1 línea AND autorizado | Specification `PUEDE_PROCESARSE` (AND de 3 Specs). Coincide con supuestos del BRD |
| `beneficio_referencia` = preferente AND total ≥ 1500 AND NOT promoción | Specification `BENEFICIO_REFERENCIA` (AND + NOT). **Solo se usa como oráculo de prueba**: no existe en el BRD (programas de lealtad fuera de alcance), por lo que no modifica precios ni el dominio |
| Total con `Decimal` | `Dinero.multiplicar` y `Dinero.sumar` |

## Resultados (evidencia en `docs/evidencias/`)

| Archivo | Resumen |
|---|---|
| `resultados_casos_prueba.csv` | 120 casos: 46 APROBADA, 14 RECHAZADA, 9 APLICA, 51 NO_APLICA |
| `resultados_transiciones_prueba.csv` | 20 transiciones: 3 FINALIZADA, 4 INSCRITA, 4 CANCELADA, 9 excepciones (6 TransicionInvalida y 3 ReglaDeNegocioViolada) |

Se regeneran con `python scripts/ejecutar_paquete_pia.py` y se verifican en `tests/integration/test_paquete_pia.py`.
Hallazgos del paquete: AUL-O013 y AUL-O039 no tienen líneas; AUL-P011 está deshabilitado (lo usan 6 operaciones: O005, O015, O020, O035, O040 y O055);
AUL-O034 a AUL-O038 pertenecen a estudiantes inactivos.
