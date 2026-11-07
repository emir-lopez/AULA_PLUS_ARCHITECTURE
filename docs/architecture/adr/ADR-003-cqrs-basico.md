# ADR-003 · CQRS básico sin bases de datos duplicadas

- **Estado:** Aceptada e implementada
- **Contexto:** la búsqueda de tutores, el detalle de sesión, la cola de Soporte, los pagos listos para liberar y los
  KPIs solo leen; no deben cargar Aggregates completos ni poder modificarlos.
- **Decisión:** *Commands* → Application Services → Aggregates → Unit of Work. *Queries* → `ConsultasAulaPlus` →
  `LecturasSql`, con SELECT específicos que devuelven DTOs (`dict`). Misma base de datos, responsabilidades separadas.
- **Consecuencias:** + lecturas simples; la API siempre responde con el *read model*. − dos caminos de acceso a las
  mismas tablas: el esquema se centraliza en `infrastructure/db.py`.
- **Trazabilidad:** US-11 (`tutores_disponibles`), US-17 (`pagos_listos_para_liberar`), NB-14 (`disputas_pendientes`),
  NB-15 (`indicadores`).
