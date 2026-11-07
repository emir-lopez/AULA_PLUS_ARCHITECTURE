# Matriz de trazabilidad: BRD → historia → regla → BPMN → componente → prueba

Cada fila se puede seguir de punta a punta. Las rutas de prueba son relativas a `tests/`.

## 1. Por regla de negocio

| Regla | NB | US | Paso BPMN | Componente (código) | Endpoint | Prueba que la verifica |
|---|---|---|---|---|---|---|
| R-01 Comisión 20 % | NB-06 | US-19 | Completar y calcular comisión | `DesgloseFinanciero.calcular`, `PorcentajeComision` | `POST /sesiones/{id}/completar` | `unit/test_value_objects_y_politicas.py::TestDesgloseFinanciero` |
| R-02 Anticipación 2 h | NB-02 | US-01 | Gateway ¿Se puede reservar? | `AnticipacionMinimaSpec` en `reserva_permitida` | `POST /sesiones` | `unit/test_specifications_y_estados.py::TestReservaPermitida`, `integration/test_servicios_sql.py::test_rechazo_hace_rollback_completo` |
| R-03 Congelamiento 10 min | NB-11 | US-02 | Congelar horario 10 min | `TransaccionSesion.reservar/confirmar_pago/expirar_congelamiento` | `POST /sesiones`, `/pago`, `/expirar` | `unit/test_aggregates.py::test_r03_*`, `integration/test_api.py::test_pago_fallido_y_expiracion` |
| R-04 Bloqueo al pagar | NB-02 | US-03 | Confirmar y bloquear agenda | `AgendaTutor.bloquear_bloque` + UoW | `POST /sesiones/{id}/pago` | `integration/test_servicios_sql.py::test_cu02_pago_confirma_y_bloquea...`, `integration/test_postgres.py::test_reservas_concurrentes...` |
| R-05 Retención 48 h | NB-07 | US-17 | Ventana 48 h → liberar | `RetencionCumplidaSpec`, `liberacion_permitida`, `ServicioLiquidacionPago` | `POST /sesiones/{id}/liberacion`, `GET /liquidaciones/pendientes` | `unit/test_aggregates.py::test_us17_*`, `integration/test_api.py::test_flujo_completo_con_fecha_simulada` |
| R-06 Reembolso 100/50/0 | NB-03 | US-07 | Cancelar sesión | `CalculadoraReembolso` | `POST /sesiones/{id}/cancelacion-estudiante` | `unit/test_value_objects_y_politicas.py::TestCalculadoraReembolso`, `unit/test_aggregates.py::TestCancelacion` |
| R-07 Cupo de sede | NB-10 | US-14 | Gateway ¿Se puede reservar? | `CupoDisponibleSpec`, `RepositorioSqlSede.obtener_para_reserva` (FOR UPDATE) | `POST /sesiones`, `POST /sedes` | `integration/test_servicios_sql.py::test_r07_*`, `integration/test_postgres.py::test_ultimo_cupo_*` |
| R-08 Mediación 72 h | NB-14 | US-16 | Soporte media disputa | `Disputa.fecha_limite`, `resolver_revision` | `POST /disputa`, `/resolucion`, `GET /soporte/disputas` | `unit/test_aggregates.py::test_cu04_*`, `integration/test_api.py::test_disputa_y_resolucion` |
| R-09 Tolerancia No-Show 10 min | NB-13 | US-15 | ¿Ambos presentes? | `TransaccionSesion.registrar_no_show` | `POST /sesiones/{id}/no-show` | `unit/test_aggregates.py::test_us15_*` |
| R-10 Perfil 7 días | NB-02 | US-11 | Buscar tutores | `PerfilVigenteSpec`, `LecturasSql.tutores_disponibles` | `GET /tutores/disponibles` | `unit/test_specifications_y_estados.py::test_fronteras_exactas`, `integration/test_api.py::test_consultas_*` |
| R-11 Evidencia | NB-01 | US-04/05/06 | Registrar evidencia / ¿suficiente? | `EvidenciaAsistencia`, `completar_con_evidencia` | `POST /sesiones/{id}/completar` | `unit/test_value_objects_y_politicas.py::TestEvidencia`, `unit/test_aggregates.py::test_us06_*` |
| R-12 Cobro en plataforma | NB-08 | US-12 | Pagar en la plataforma | `PagoIn` (resultado de pasarela), `confirmar_pago` | `POST /sesiones/{id}/pago` | `integration/test_api.py::test_201_reserva_y_200_pago` |
| R-13 Compensación 100 % | NB-04 | US-08 | No-Show / cancelación del tutor | `PoliticaCompensacion`, `cancelar_por_tutor` | `/cancelacion-tutor`, `/no-show` | `unit/test_aggregates.py::test_us08_*` |
| R-14 Suspensión por marcas | NB-05 | US-09 | Marca de incumplimiento | `AgendaTutor.registrar_incumplimiento`, `PoliticaSuspension`, `TutorSuspendidoSpec` | `/no-show`, `/cancelacion-tutor` | `unit/test_aggregates.py::test_us09_*`, `integration/test_servicios_sql.py::test_us09_*` |
| R-15 Ventana de disputa | NB-14 | US-16 | ¿Disputa abierta? | `abrir_disputa` (VentanaDeDisputaCerrada) | `POST /sesiones/{id}/disputa` | `unit/test_aggregates.py::test_validaciones_de_disputa` |
| R-16 Cancelación tardía | NB-05 | US-09 | Tutor cancela | `cancelar_por_tutor` (tardía ≤24 h) | `/cancelacion-tutor` | `integration/test_servicios_sql.py::test_cancelacion_tardia_del_tutor_suma_marca` |
| KPIs | NB-15 | — | — | `LecturasSql.indicadores` | `GET /indicadores` | `integration/test_servicios_sql.py::test_flujo_completo_hasta_liberacion_y_kpis` |
| Calificación | — | US-18 | Calificación mutua (AS-IS) | `TransaccionSesion.calificar` | `POST /calificacion` | `unit/test_aggregates.py::test_us18_calificar` |

## 2. Cobertura de necesidades (NB) del BRD

| NB | Cobertura | Dónde |
|---|---|---|
| NB-01 Evidencia | ✅ Completa | R-11, US-04/05/06 |
| NB-02 Disponibilidad real | ✅ Completa | R-02, R-04, R-10 |
| NB-03 Reembolsos | ✅ Completa | R-06 |
| NB-04 Compensación por tutor | ✅ Completa | R-13 |
| NB-05 Incumplimientos | ✅ Completa (umbral = supuesto configurable) | R-14, R-16 |
| NB-06 Comisión | ✅ Completa | R-01 |
| NB-07 Liberación | ✅ Completa | R-05 |
| NB-08 Extensiones en plataforma | ⚠️ Parcial: cobro en plataforma sí; extensión (US-12) en backlog | R-12 |
| NB-09 Fallas de conexión | ⏳ Backlog (US-13) | — |
| NB-10 Sobrecupo | ✅ Completa, con prueba de concurrencia | R-07 |
| NB-11 Congelamiento | ✅ Completa | R-03 |
| NB-12 Reasignación | ⏳ Backlog (US-10); se compensa al 100 % mientras tanto | R-13 |
| NB-13 No-Show | ✅ Completa | R-09 |
| NB-14 Disputas | ✅ Completa | R-08, R-15 |
| NB-15 KPIs | ✅ Completa | `GET /indicadores` |

**Resultado:** 12 de 15 necesidades completas, 1 parcial y 2 en backlog. De 19 historias, 16 están implementadas y
probadas. Los pendientes se documentan, no se ocultan.

## 3. Casos de uso de U3 → implementación

| CU | Servicio / método | Endpoint |
|---|---|---|
| CU-01 Reservar sesión | `ServicioReservaSesion.reservar_sesion` | `POST /sesiones` |
| CU-02 Confirmar pago / vencer | `confirmar_pago_reserva`, `registrar_pago_fallido`, `expirar_congelamiento` | `POST /sesiones/{id}/pago`, `/expirar` |
| CU-03 Cancelar | `ServicioCancelacionSesion.cancelar_por_estudiante` / `cancelar_por_tutor` | `/cancelacion-estudiante`, `/cancelacion-tutor` |
| CU-04 Abrir disputa | `ServicioDisputaSesion.abrir_disputa` / `resolver` | `/disputa`, `/resolucion` |
| CU-05 Liberar pago | `ServicioLiquidacionPago.liberar_pago_al_tutor` / `liberar_pendientes` | `/liberacion` |
| H-15 Completar sesión (nuevo) | `ServicioEjecucionSesion.completar_sesion` | `/completar` |

## 4. Hallazgos de U3

| Hallazgo | Estado en el PIA | Decisión |
|---|---|---|
| H-01 Retención 48/72 h | Cerrado | ADR-004 |
| H-04 "Porcentaje asignado al tutor" | Cerrado | 20 % fijo en `PorcentajeComision` |
| H-05 Bordes de reembolso | Cerrado | ADR-004 |
| H-06 Cupo atómico | Cerrado | ADR-006 |
| H-07 Umbral de suspensión | Supuesto configurable | ADR-004 |
| H-10 Estudiante ausente | Parcial: sin reembolso, pago retenido | BRD supuesto 8 |
| H-11 Pago tardío | Cerrado | ADR-005 |
| H-13 Pago fallido | Cerrado | ADR-005, evento `PagoRechazado` |
| H-15 Servicio de completar | Cerrado | `ServicioEjecucionSesion` |
