# ADR-002 · Unit of Work local + outbox transaccional para Domain Events

- **Estado:** Aceptada e implementada
- **Contexto:** reservar, confirmar pago, expirar y cancelar modifican **dos** Aggregates (sesión y agenda). Si se
  guardan por separado puede quedar una sesión Confirmada con el bloque aún Congelado. Publicar eventos antes del
  commit anunciaría hechos que pueden revertirse.
- **Alternativas:** guardar cada raíz por separado y publicar directo (estados parciales) · transacción distribuida
  (innecesaria: una sola base) · **UoW + outbox** (elegida).
- **Decisión:** `UnidadDeTrabajoSql` abre una sesión SQLAlchemy por caso de uso. `confirmar()` extrae los eventos de
  todos los Aggregates tocados, los inserta en `eventos_outbox` y hace un único COMMIT. Con excepción o sin
  confirmar: ROLLBACK. Concurrencia **optimista** con columna `version` en `agendas` y `sesiones`
  (`UPDATE … WHERE version = :leida`; 0 filas → `ConflictoDeVersion` → HTTP 409).
- **Consecuencias:** + todo-o-nada verificable (`test_outbox_no_guarda_eventos_si_la_operacion_falla`,
  `test_conflicto_de_version_optimista`, `test_reservas_concurrentes_*` en PostgreSQL). − falta el *relay* que
  publique el outbox a un broker (fuera de alcance; la columna `publicado` queda lista).
- **Fuera del commit:** el cobro en la pasarela ocurre antes; la API solo recibe su resultado (R-12).
