# ADR-001 · Domain Model con dos Aggregates para el núcleo transaccional

- **Estado:** Aceptada (U3, etapa 2) · implementada en el PIA
- **Contexto:** reserva, pago, cancelación, disputa y liberación comparten reglas de tiempo (2 h, 10 min, 48 h, 72 h),
  dinero (20 %, reembolsos) y estado. Las mismas invariantes deben valer en todos los casos de uso y canales.
- **Alternativas:**
  1. *Transaction Script*: simple al inicio, pero repite validaciones en cada flujo.
  2. *Table Module*: agrupa por tabla; las reglas que cruzan sesión y agenda quedan dispersas.
  3. *Domain Model* (elegida).
- **Decisión:** dos raíces con límites de consistencia separados: `TransaccionSesion` (sesión, pago, reembolso,
  disputa, desglose) y `AgendaTutor` (bloques, marcas, suspensión). Se relacionan por identificadores (`tutor_id`,
  `bloque_id`, `sesion_id`), nunca por referencia de objeto. Las reglas compuestas viven en Specifications y Domain
  Services (`CalculadoraReembolso`, `PoliticaCompensacion`, `PoliticaSuspension`).
- **Consecuencias:** + invariantes concentradas y probadas sin base de datos (154 pruebas unitarias en milisegundos).
  − más tipos y mapeo objeto-relacional explícito en `infrastructure/repositories.py`.
- **Trazabilidad:** R-01…R-16 · CU-01…CU-05 · `src/domain/sesion.py`, `src/domain/agenda.py`.
