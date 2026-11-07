# ADR-006 · Control atómico del cupo de sede compartido entre tutores (H-06)

- **Estado:** Aceptada e implementada
- **Contexto:** varios tutores distintos pueden reservar en la misma sede y horario. El versionado de `AgendaTutor`
  protege el bloque de **un** tutor, pero no el último cupo compartido: un `COUNT` aislado permite sobrecupo si dos
  transacciones cuentan al mismo tiempo.
- **Alternativas:** COUNT sin bloqueo (sobrecupo) · Aggregate `OcupacionSede` con contador (más tablas) ·
  **bloqueo pesimista de la fila de la sede** (elegida).
- **Decisión:** `RepositorioSqlSede.obtener_para_reserva` hace `SELECT … FOR UPDATE` sobre la sede; dentro de la misma
  transacción se cuenta la ocupación y se evalúa `CupoDisponibleSpec`. La segunda transacción espera el COMMIT de la
  primera y ve el conteo actualizado.
- **Consecuencias:** + verificado en PostgreSQL con 3 hilos y cupo 1
  (`test_ultimo_cupo_de_sede_entre_tutores_distintos`). − serializa reservas de la misma sede (aceptable por volumen).
  SQLite ignora `FOR UPDATE`; por eso la prueba concurrente corre solo contra PostgreSQL (Docker/CI).
