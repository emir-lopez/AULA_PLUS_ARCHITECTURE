# User Stories y criterios de aceptación (Gherkin) — AulaPlus

19 historias (mínimo exigido: 15). Cada escenario indica la **prueba automatizada** que lo verifica.
Estado: ✅ implementada y probada · ⏳ backlog documentado.

---

## US-01 — Reserva con anticipación mínima ✅ (R-02, NB-02)
Como **estudiante**, quiero reservar una sesión con al menos 2 horas de anticipación, para que mi solicitud se procese oportunamente.

```gherkin
Escenario: Reserva con anticipación suficiente
  Dado un bloque Disponible que inicia en 2 horas exactas
  Cuando el estudiante lo reserva
  Entonces la sesión queda Reservada y el bloque Congelado

Escenario: Reserva tardía rechazada
  Dado un bloque que inicia en 1 hora 59 minutos
  Cuando el estudiante intenta reservarlo
  Entonces el sistema responde 422 "AnticipacionInsuficiente"
  Y el bloque sigue Disponible y no se crea la sesión
```
Pruebas: `test_specifications_y_estados.py::TestReservaPermitida`, `test_servicios_sql.py::test_rechazo_hace_rollback_completo`

## US-02 — Pago con congelamiento temporal ✅ (R-03, NB-11)
Como **estudiante**, quiero pagar mientras el horario se congela, para que nadie más lo tome durante el pago.

```gherkin
Escenario: Pago dentro del congelamiento
  Dado una sesión Reservada a las 12:00 por 350.00 MXN
  Cuando la pasarela confirma 350.00 MXN a las 12:10:00
  Entonces la sesión pasa a Confirmada

Escenario: Pago vencido
  Dado una sesión Reservada a las 12:00
  Cuando el pago llega a las 12:10:01
  Entonces el sistema responde 422 "CongelamientoVencido" sin cambiar el estado

Escenario: Vencimiento sin pago
  Dado una sesión Reservada sin pago después de 10 minutos
  Cuando el temporizador ejecuta la expiración
  Entonces la sesión queda Cancelada y el bloque vuelve a Disponible
```
Pruebas: `test_aggregates.py::TestReservaYPago::test_r03_*`, `test_servicios_sql.py::test_cu02_vencimiento_libera_el_bloque`

## US-03 — Bloqueo automático de disponibilidad ✅ (R-04, NB-02)
Como **tutor**, quiero que mi disponibilidad se bloquee al confirmarse el pago, para evitar reservas simultáneas.

```gherkin
Escenario: Bloqueo al confirmar
  Dado un bloque Congelado por la sesión S-1
  Cuando se confirma el pago íntegro de S-1
  Entonces el bloque pasa a Bloqueado y se emiten PagoConfirmado, SesionConfirmada y HorarioBloqueado

Escenario: Reservas simultáneas
  Dado cinco estudiantes que reservan el mismo bloque al mismo tiempo
  Cuando las cinco transacciones se ejecutan en PostgreSQL
  Entonces solo una reserva se crea y las demás reciben HorarioNoDisponible o ConflictoDeVersion
```
Pruebas: `test_servicios_sql.py::test_cu02_pago_confirma_y_bloquea...`, `test_postgres.py::test_reservas_concurrentes...`

## US-04 — Registro de conexión en sesión en línea ✅ (R-11, NB-01)
Como **tutor**, quiero registrar mi conexión a una sesión en línea, para confirmar que la sesión se realizó.

```gherkin
Escenario: Evidencia en línea completa
  Dado una sesión en línea Confirmada que ya terminó
  Y existen timestamps de conexión del tutor y del estudiante y confirmación mutua
  Cuando se registra la evidencia
  Entonces la sesión pasa a Completada y se calcula la comisión
```
Pruebas: `test_value_objects_y_politicas.py::TestEvidencia`, `test_aggregates.py::test_us19_*`

## US-05 — Check-in por geolocalización ✅ (R-11, NB-01)
Como **estudiante**, quiero hacer check-in por geolocalización en una sesión presencial, para confirmar mi asistencia.

```gherkin
Escenario: Check-in dentro de la geocerca
  Dado una sesión presencial Confirmada
  Cuando el check-in del estudiante está dentro del radio de la sede y ambos confirman
  Entonces la evidencia es suficiente para completar la sesión

Escenario: Check-in fuera de la geocerca
  Cuando el check-in no está dentro del radio
  Entonces la evidencia es insuficiente
```
Pruebas: `test_value_objects_y_politicas.py::TestEvidencia::test_presencial_*`

## US-06 — Revisión de Soporte por confirmación faltante ✅ (R-11, NB-01)
Como **soporte**, quiero revisar una sesión cuando falte la confirmación de una parte, para determinar su estado.

```gherkin
Escenario: Falta confirmación
  Dado una sesión Confirmada que terminó con evidencia incompleta
  Cuando se registra la evidencia
  Entonces la sesión pasa a EnRevision con motivo "EvidenciaInsuficiente"

Escenario: Soporte resuelve a favor del tutor
  Dado una sesión EnRevision por evidencia
  Cuando Soporte resuelve a favor del tutor
  Entonces la sesión pasa a Completada y se calcula la comisión
```
Pruebas: `test_aggregates.py::test_us06_evidencia_insuficiente_va_a_revision`

## US-07 — Cancelación con reembolso según anticipación ✅ (R-06, NB-03)
Como **estudiante**, quiero cancelar una sesión reservada, para recibir el reembolso que corresponda.

```gherkin
Esquema del escenario: Reembolso escalonado
  Dado una sesión Confirmada de 200.00 MXN
  Cuando el estudiante cancela <horas> horas antes del inicio
  Entonces el reembolso es <reembolso> MXN y el bloque se libera

  Ejemplos:
    | horas | reembolso |
    | 48    | 200.00    |
    | 24.01 | 200.00    |
    | 24    | 100.00    |
    | 6     | 100.00    |
    | 5.99  | 0.00      |
```
Pruebas: `test_value_objects_y_politicas.py::TestCalculadoraReembolso`, `test_aggregates.py::TestCancelacion`

## US-08 — Compensación por cancelación o No-Show del tutor ✅ (R-13, NB-04)
Como **estudiante**, quiero recibir compensación cuando el tutor cancele o no se presente.

```gherkin
Escenario: El tutor cancela
  Dado una sesión Confirmada de 350.00 MXN
  Cuando el tutor la cancela antes del inicio
  Entonces el estudiante recibe 350.00 MXN y el pago queda Reembolsado

Escenario: El tutor no se presenta
  Dado una sesión Confirmada
  Cuando se registra No-Show del tutor tras 10 minutos de tolerancia
  Entonces el estudiante recibe el 100 %
```
Pruebas: `test_aggregates.py::test_us08_*`, `test_us15_*`

## US-09 — Marcas de incumplimiento y suspensión ✅ (R-14, R-16, NB-05)
Como **administrador**, quiero registrar marcas de incumplimiento y suspender al tutor, para gestionar incumplimientos.

```gherkin
Escenario: Tercera marca suspende
  Dado un tutor con 2 marcas
  Cuando incurre en un No-Show
  Entonces acumula 3 marcas, queda suspendido y se emite TutorSuspendido
  Y su perfil deja de aparecer en la búsqueda y no acepta reservas
```
Pruebas: `test_aggregates.py::test_us09_tercera_marca_suspende`, `test_servicios_sql.py::test_us09_tres_no_show_*`

## US-10 — Reasignación automática de tutor ⏳ (NB-12)
Como **estudiante**, quiero una reasignación automática tras la cancelación del tutor con el pago procesado.

```gherkin
Escenario: Hay otro tutor disponible
  Dado un tutor que cancela una sesión pagada
  Cuando existe otro tutor disponible en la misma materia y horario
  Entonces la sesión se reasigna sin nuevo cobro
```
Estado: backlog. Mientras tanto se aplica R-13 (compensación 100 %). Diseño: Domain Service `SeleccionadorTutorReemplazo` (U3).

## US-11 — Ocultar perfil con disponibilidad desactualizada ✅ (R-10, NB-02)
Como **administrador**, quiero ocultar perfiles con agenda desactualizada.

```gherkin
Escenario: Perfil vencido
  Dado un tutor que actualizó su agenda hace 7 días y 1 segundo
  Cuando un estudiante busca tutores o intenta reservar
  Entonces el perfil no aparece y la reserva se rechaza con "PerfilNoVisible"
```
Pruebas: `test_specifications_y_estados.py::TestReservaPermitida`, `test_api.py::test_consultas_de_disponibilidad_y_sede`

## US-12 — Extensión de sesión ⏳ (NB-08, R-12)
Como **estudiante**, quiero extender una sesión en curso, pagando dentro de la plataforma.
Estado: backlog; el cobro reutilizaría `Dinero` y el flujo de pago de CU-02.

## US-13 — Falla de conexión ⏳ (NB-09)
Como **soporte**, quiero registrar fallas de conexión y aplicar la tolerancia de 15 minutos.
Estado: backlog; se modelaría como evento `FallaDeConexionReportada` y transición a `EnRevision`.

## US-14 — Reserva presencial condicionada a cupo ✅ (R-07, NB-10)
Como **estudiante**, quiero reservar una sesión presencial solo si hay cupo, para evitar sobrecupo.

```gherkin
Escenario: Último cupo disputado por dos tutores distintos
  Dado una sede con cupo máximo 1
  Cuando tres estudiantes reservan al mismo tiempo con tres tutores distintos
  Entonces solo una reserva se crea y las otras reciben "SinCupoEnSede"
```
Pruebas: `test_servicios_sql.py::test_r07_cupo_de_sede_presencial`, `test_postgres.py::test_ultimo_cupo_de_sede_entre_tutores_distintos`

## US-15 — Registro de No-Show ✅ (R-09, NB-13)
Como **tutor**, quiero registrar la inasistencia de una parte.

```gherkin
Escenario: Antes de la tolerancia
  Dado una sesión Confirmada que inició hace 9 minutos
  Cuando se intenta registrar No-Show
  Entonces el sistema responde "ToleranciaNoCumplida"

Escenario: Después de la tolerancia
  Cuando han pasado 10 minutos
  Entonces la sesión pasa a NoShow y se emite NoShowRegistrado
```
Pruebas: `test_aggregates.py::test_us15_no_show_tras_tolerancia_de_10_minutos`

## US-16 — Apertura de disputa ✅ (R-08, R-15, NB-14)
Como **estudiante**, quiero abrir una disputa sobre una sesión, para solicitar su revisión.

```gherkin
Escenario: Disputa dentro de la ventana
  Dado una sesión Completada hace 1 hora
  Cuando el estudiante abre una disputa con motivo
  Entonces la sesión pasa a EnRevision con fecha límite de mediación de 72 horas

Escenario: Fuera de la ventana
  Dado una sesión Completada hace 49 horas
  Cuando se intenta abrir disputa
  Entonces el sistema responde "VentanaDeDisputaCerrada"
```
Pruebas: `test_aggregates.py::TestDisputaYLiquidacion`

## US-17 — Liberación de pago al concluir la ventana ✅ (R-05, NB-07)
Como **tutor**, quiero recibir el pago al concluir la ventana de disputas.

```gherkin
Escenario: Retención cumplida sin disputa
  Dado una sesión Completada hace 48 horas sin disputa abierta
  Cuando la plataforma ejecuta la liberación
  Entonces el pago pasa a Liberado con neto 280.00 de 350.00 y se emite FondosLiberados

Escenario: Retención vigente
  Dado una sesión Completada hace 47 h 59 min
  Entonces la liberación se rechaza con "RetencionVigente"

Escenario: Disputa abierta
  Dado una disputa abierta
  Entonces la liberación se rechaza con "DisputaAbierta"
```
Pruebas: `test_aggregates.py::test_us17_*`, `test_r05_*`, `test_api.py::test_flujo_completo_con_fecha_simulada`

## US-18 — Calificación de sesión ✅
Como **estudiante**, quiero calificar una sesión completada.

```gherkin
Escenario: Calificar una vez
  Dado una sesión Completada
  Cuando el estudiante la califica con 5
  Entonces se registra la calificación
  Y un segundo intento responde "SesionYaCalificada"
```
Pruebas: `test_aggregates.py::test_us18_calificar`

## US-19 — Cálculo automático de comisión ✅ (R-01, NB-06)
Como **administrador**, quiero que el sistema calcule la comisión al completar una sesión.

```gherkin
Esquema del escenario: Comisión del 20 %
  Dado una sesión de <bruto> MXN
  Cuando la sesión pasa a Completada
  Entonces la comisión es <comision> y el neto del tutor <neto>
  Y comisión + neto = bruto

  Ejemplos:
    | bruto  | comision | neto   |
    | 350.00 | 70.00    | 280.00 |
    | 99.99  | 20.00    | 79.99  |
    | 0.01   | 0.00     | 0.01   |
```
Pruebas: `test_value_objects_y_politicas.py::TestDesgloseFinanciero`
