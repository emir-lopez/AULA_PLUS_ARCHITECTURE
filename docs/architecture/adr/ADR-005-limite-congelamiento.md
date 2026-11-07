# ADR-005 · Límite inclusivo del congelamiento de 10 minutos

- **Estado:** Aceptada (PIA)
- **Contexto:** el código base de U3 rechazaba un pago a los 10:00 exactos (`ahora >= congelado_hasta`), mientras que
  la Regla 2 de AF5 (U5) lo aceptaba (caso PIA-R2-03). El BRD dice "durante 10 minutos" sin precisar el borde.
- **Decisión:** el congelamiento **incluye** el instante final: `confirmar_pago` acepta `ahora <= congelado_hasta` y
  `expirar_congelamiento` solo actúa cuando `ahora > congelado_hasta`. No existe un instante en que ambas operaciones
  sean válidas a la vez.
- **Consecuencias:** pruebas de frontera `test_r03_limite_inclusivo_minuto_10_exacto` y
  `test_r03_un_segundo_despues_se_rechaza_sin_cambios`. Pendiente de confirmar con el stakeholder.
- **H-11 (pago tardío):** se rechaza con `CongelamientoVencido`; la devolución corresponde a la pasarela.
- **H-13 (pago fallido):** se registra el evento `PagoRechazado` y la reserva sigue congelada para reintentar.
