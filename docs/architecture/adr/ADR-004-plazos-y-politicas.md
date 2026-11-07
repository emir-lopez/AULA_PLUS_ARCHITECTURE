# ADR-004 · Cierre de los hallazgos de política H-01, H-05 y H-07

- **Estado:** Aceptada (PIA). Cierra hallazgos abiertos en U3.
- **H-01 Retención 48 h vs. 72 h.** El BRD (restr. 6) y la entrevista dicen 48 h tras Completada; el diseño previo
  usaba 72 h. **Decisión:** dos relojes distintos: `HORAS_RETENCION=48` para liberar el pago y `HORAS_MEDIACION=72`
  como plazo máximo de una disputa. La disputa solo puede abrirse dentro de la ventana de 48 h (R-15).
- **H-05 Reembolso.** Entrevista: 100 % con más de 24 h, 50 % entre 24 y 6 h, 0 % con menos de 6 h.
  **Fronteras:** `> 24 h → 100 %`, `6 h ≤ x ≤ 24 h → 50 %`, `< 6 h → 0 %` (igual que la Regla 3 de AF5).
  Se prueban 24.01, 24, 6 y 5.99 h.
- **H-07 Umbral de suspensión.** No confirmado por el stakeholder. Valor de trabajo `MARCAS_PARA_SUSPENSION=3`,
  configurable por entorno.
- **Consecuencias:** las políticas son objetos inyectados (OCP): cambiar un porcentaje no toca los Aggregates. Todos
  los valores son variables de entorno (12-Factor).
