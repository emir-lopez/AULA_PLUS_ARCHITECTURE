# BRD — AulaPlus (Caso 08) · versión PIA 2.0

| Campo | Valor |
|---|---|
| Materia | Componentes de Lógica de Negocio — FIME, UANL |
| Profesor | Miguel Ángel Gómez Marroquín |
| Equipo 8 | Andrés Caleb Leija Pedroza (2144830) · David Alonso Torres Guerrero (2144813) · Emir Misael López Pérez (2150561) |
| Versión | 2.0 (refinada para el PIA, 6 de noviembre de 2026). v1.0: 3 de septiembre de 2026 (U2) |

> **Qué cambió respecto a la v1.0 (U2).** Se renumeraron restricciones para que coincidan con la matriz de validación,
> se incorporó la anticipación mínima de 2 h (estaba solo en US-01), se agregaron los porcentajes de reembolso
> obtenidos en la entrevista, y se cerraron los hallazgos H-01, H-05, H-06, H-11, H-13 y H-15 de la Unidad 3 con
> decisiones documentadas en los ADR. Ver [§11 Control de cambios](#11-control-de-cambios).

## 1. Propósito

Documentar, desde la perspectiva del negocio, qué necesita resolver AulaPlus y por qué, como fuente única de verdad
para la arquitectura (`docs/architecture/`), el código (`src/`) y las pruebas (`tests/`). Cada regla tiene un ID
(`R-xx`) que se rastrea hasta el código en la [matriz de trazabilidad](architecture/trazabilidad.md).

## 2. Contexto del negocio

AulaPlus es una plataforma de intermediación (marketplace) que conecta **estudiantes** con **tutores** particulares
para sesiones **presenciales** o **en línea**. Su ingreso es una **comisión del 20 %** por sesión realizada.

**Operación actual (AS-IS):** el tutor registra disponibilidad y materias → el estudiante elige materia, modalidad,
fecha y horario → reserva y paga → se imparte la sesión → ambas partes se califican → la plataforma debe conservar
evidencia y pagar al tutor descontando su comisión. Las excepciones (cancelaciones, ausencias, fallas de conexión,
extensiones) hoy se atienden manualmente.

**Actores:** Estudiante · Tutor · Plataforma/Administración · Soporte · Finanzas (stakeholder interno).

## 3. Problema y oportunidad

| Problema observado | Consecuencia | Oportunidad |
|---|---|---|
| No hay prueba objetiva de que la sesión ocurrió | Disputas manuales, pagos retrasados | Evidencia verificable (conexión, geocerca, confirmación mutua) |
| Disponibilidades desactualizadas | Reservas de horarios inexistentes, reembolsos evitables | Ocultar perfiles sin actualizar y bloquear horarios automáticamente |
| Cancelaciones caso por caso | Criterio inconsistente, costo operativo | Políticas automáticas de reembolso y penalización |
| Cálculo manual de reembolsos y pagos | Errores contables | Cálculo automático de comisión, neto y reembolso con `Decimal` |

## 4. Stakeholders

| Stakeholder | Tipo | Interés | Influencia |
|---|---|---|---|
| Estudiante | Externo | Reservar con confianza y recibir reembolsos justos | Media |
| Tutor | Externo | Gestionar agenda y cobrar a tiempo | Media |
| Administración AulaPlus | Interno | Operación, ingresos por comisión, menos disputas | Alta |
| Soporte | Interno | Validar sesiones en revisión y mediar disputas en plazo | Alta |
| Finanzas | Interno | Comisiones, reembolsos y dispersión correctas | Alta |
| Desarrollo / TI | Interno | Implementar reglas trazables | Media |

## 5. Alcance

**Incluye (implementado en el PIA):** reserva en línea y presencial con control de cupo · gestión de disponibilidad ·
congelamiento de horario durante el pago · confirmación de pago y bloqueo de agenda · registro de pago fallido ·
cancelación por estudiante con reembolso escalonado · cancelación del tutor con compensación · evidencia de asistencia
y revisión por Soporte · No-Show · comisión 20 % y neto · retención de 48 h y liberación · disputas con mediación de
72 h · marcas de incumplimiento y suspensión · calificación · KPIs.

**Incluye pero no implementado en esta versión (backlog):** reasignación automática de tutor (US-10), extensión de
sesión (US-12) y gestión de fallas de conexión con pausa de 15 min (US-13). Se conservan como requisitos; ver
[trazabilidad](architecture/trazabilidad.md).

**No incluye:** nuevos métodos de pago, expansión internacional/otras monedas, mensajería, videoconferencia propia,
programas de lealtad, gestión académica de contenidos, contratación de tutores.

## 6. Necesidades del negocio

| ID | Necesidad | Justificación |
|---|---|---|
| NB-01 | Evidencia verificable de que la sesión se realizó | Reduce disputas y libera pagos con certeza |
| NB-02 | Mostrar solo horarios realmente disponibles | Evita cancelaciones por calendarios desactualizados |
| NB-03 | Reembolso automático según anticipación de la cancelación | Consistencia y menos errores |
| NB-04 | Compensar al estudiante cuando el tutor incumple | Confianza en la plataforma |
| NB-05 | Controlar y registrar incumplimientos de tutores | Estándares de calidad |
| NB-06 | Calcular automáticamente la comisión de cada sesión | Garantiza el modelo de ingresos |
| NB-07 | Liberar y dispersar pagos a tutores según política | Trazabilidad financiera |
| NB-08 | Extensiones de sesión solo dentro de la plataforma | Protege ingresos por comisión |
| NB-09 | Reglas uniformes ante interrupciones de conexión | Menos incertidumbre |
| NB-10 | Prevenir sobrecupo en sedes presenciales | Evita conflictos logísticos |
| NB-11 | Reservar temporalmente el horario durante el pago | Evita doble asignación |
| NB-12 | Reasignar sesión si el tutor cancela con pago procesado | Minimiza afectación al estudiante |
| NB-13 | Identificar y gestionar No-Show | Penalización y reembolso consistentes |
| NB-14 | Proceso formal de reclamos y disputas | Transparencia |
| NB-15 | Indicadores operativos y financieros | Decisiones basadas en datos |

> **Corrección de U3:** la matriz de U3 usaba otra numeración (NB-08 = cupo, NB-12 = disputas). En el PIA rige la
> numeración de esta tabla, que es la del BRD original.

## 7. Reglas de negocio y restricciones

| ID | Regla | Valor | Fuente | Estado |
|---|---|---|---|---|
| R-01 | Comisión de AulaPlus sobre cada sesión completada; el tutor recibe el neto | 20 % | Entrevista, BRD v1 restr. 7 | Validada |
| R-02 | Anticipación mínima para reservar | 2 h | US-01 | Validada |
| R-03 | Congelamiento del horario durante el pago | 10 min (límite inclusivo, ADR-005) | Restr. 10 | Validada |
| R-04 | Al confirmar el pago, el horario pasa a Bloqueado | — | Restr. 4, US-03 | Validada |
| R-05 | Retención del pago antes de liberarlo al tutor | 48 h desde Completada (ADR-004) | Restr. 6 | Validada (H-01 cerrado) |
| R-06 | Reembolso por cancelación del estudiante | >24 h: 100 % · 6–24 h: 50 % · <6 h: 0 % | Entrevista U2 | Validada (H-05 cerrado) |
| R-07 | Sesión presencial solo si hay cupo en la sede | `cupo_maximo` por sede | US-14 | Validada (H-06 cerrado) |
| R-08 | Plazo máximo de mediación de una disputa | 72 h | Restr. 11 | Validada |
| R-09 | Tolerancia para declarar No-Show | 10 min | Restr. 9 | Validada |
| R-10 | Perfil sin actualizar su calendario se oculta | 7 días | Restr. 3 | Validada |
| R-11 | Completar requiere evidencia (conexión/geocerca + confirmación mutua); si falta, va a revisión | — | US-04/05/06 | Validada |
| R-12 | Todos los cobros dentro de la plataforma | — | Restr. 1 y 2 | Validada |
| R-13 | Si el tutor cancela o no se presenta, el estudiante recibe el 100 % | 100 % | US-08 | Validada |
| R-14 | Marcas de incumplimiento; suspensión al alcanzar el umbral | 3 marcas (parámetro) | US-09, H-07 | Supuesto configurable |
| R-15 | La disputa solo se abre dentro de la ventana de retención y con pago aún no liberado | 48 h | Glosario "Ventana de disputas" | Validada |
| R-16 | Una cancelación del tutor con ≤24 h de anticipación es tardía y genera marca | 24 h | Glosario "Penalizaciones" | Supuesto (S-09) |

Restricciones adicionales: tolerancia de falla de conexión de 15 min (backlog US-13); montos en MXN con dos decimales.
Todos los plazos son variables de entorno (`.env.example`) para cambiarlos sin tocar código (12-Factor).

## 8. Supuestos

1. Los usuarios tienen un método de pago válido; la pasarela devuelve *Confirmado* o *Fallido*.
2. Los dispositivos permiten geolocalización en modalidad presencial (la app informa si el check-in está en la geocerca).
3. La infraestructura registra timestamps confiables de conexión.
4. Soporte dispone de una interfaz administrativa (en el PIA: endpoints `/soporte/disputas` y `/resolucion`).
5. El monto de la sesión = tarifa por hora del tutor × duración del bloque.
6. Un pago fallido no cancela la reserva: puede reintentarse mientras dure el congelamiento (H-13).
7. Un pago que llega después de vencido el congelamiento se rechaza y la devolución la gestiona la pasarela (H-11).
8. Si el ausente es el estudiante, no hay reembolso y el pago no se libera automáticamente (política pendiente H-10).
9. Cancelación tardía del tutor = 24 h o menos antes del inicio.

## 9. Criterios de éxito (KPIs, endpoint `GET /indicadores`)

| KPI (confirmado por el stakeholder) | Meta propuesta por el equipo |
|---|---|
| Tasa de sesiones completadas vs. canceladas/disputadas | ≥ 90 % completadas; disputas < 5 % |
| Tiempo de resolución de disputas | Promedio < 48 h; 95 % antes de 72 h |
| Ingreso por comisiones y % de reembolsos | Cálculo exacto (0 diferencias de centavos) y visibilidad permanente |

## 10. Glosario breve

Ver el [glosario de dominio completo](glosario.md) (lenguaje ubicuo, 30 términos).

## 11. Control de cambios

| Cambio | Origen | Decisión |
|---|---|---|
| Restricciones renumeradas y R-02 (2 h) agregada | Validación U2 citaba restricciones con otra numeración | Tabla §7 con IDs `R-xx` estables |
| Porcentajes de reembolso | Hallazgo H-05 | 100/50/0 con fronteras 24 h (50 %) y 6 h (50 %) — ADR-004 |
| Retención 48 h vs. 72 h | Hallazgo H-01 | 48 h retención; 72 h es plazo de mediación — ADR-004 |
| Cupo compartido de sede | Hallazgo H-06 | Bloqueo pesimista de la fila de sede + conteo en la misma transacción — ADR-006 |
| Borde de los 10 min | Diferencia código U3 vs. U5 | Inclusivo: a los 10:00 exactos se acepta — ADR-005 |
| Completar sesión | Hallazgo H-15 | Caso de uso `completar` con evidencia; sin evidencia → EnRevision |
| "Demanda" duplicaba "Comisión" | Glosario U2 | Definición corregida |
| US-19 "porcentaje asignado al tutor" | Hallazgo H-04 | 20 % fijo en `PorcentajeComision`, el porcentaje viaja con el desglose |
