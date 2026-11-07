# Máquinas de estado

Fuente única de verdad: `src/domain/state_machine.py` (`TRANSICIONES_SESION`, `TRANSICIONES_BLOQUE`).
Toda combinación (estado, acción) que no aparece aquí lanza `TransicionInvalida` → HTTP 409 sin modificar nada.
La matriz completa 6 estados × 10 acciones (60 casos) se prueba en `test_specifications_y_estados.py::test_matriz_completa_6x10`.

## Sesión (`EstadoSesion`)

```mermaid
stateDiagram-v2
  [*] --> Reservada : reservar (R-02, R-07, R-10)
  Reservada --> Confirmada : confirmar_pago (≤10 min, monto íntegro)
  Reservada --> Cancelada : expirar (>10 min sin pago)
  Confirmada --> Cancelada : cancelar_por_estudiante (reembolso 100/50/0)
  Confirmada --> Cancelada : cancelar_por_tutor (reembolso 100 % + marca)
  Confirmada --> Completada : completar (evidencia suficiente, comisión 20 %)
  Confirmada --> EnRevision : enviar_a_revision (evidencia insuficiente)
  Confirmada --> NoShow : registrar_no_show (≥10 min de tolerancia)
  Completada --> EnRevision : abrir_disputa (≤48 h, mediación 72 h)
  EnRevision --> Completada : resolver_a_favor_tutor
  EnRevision --> Cancelada : resolver_a_favor_estudiante (reembolso 100 %)
  Completada --> [*] : liberar_fondos (48 h, sin disputa) — pago Liberado
  Cancelada --> [*]
  NoShow --> [*]
```

## Pago (`EstadoPago`)

```mermaid
stateDiagram-v2
  [*] --> Pendiente
  Pendiente --> Confirmado : PagoConfirmado
  Confirmado --> Liberado : FondosLiberados
  Confirmado --> Reembolsado : reembolso 100 %
  Confirmado --> ReembolsoParcial : reembolso 50 %
```

## Bloque de agenda (`EstadoBloque`)

```mermaid
stateDiagram-v2
  [*] --> Disponible
  Disponible --> Congelado : congelar (reserva)
  Congelado --> Bloqueado : bloquear (pago confirmado)
  Congelado --> Disponible : liberar (vencimiento)
  Bloqueado --> Disponible : liberar (cancelación)
```

## Correspondencia con el paquete de datos del PIA

| Paquete (inscripciones) | AulaPlus |
|---|---|
| PREINSCRITA | Reservada |
| VALIDADA / INSCRITA | Confirmada |
| FINALIZADA | Completada |
| CANCELADA | Cancelada |
