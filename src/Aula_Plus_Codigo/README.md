# Entregable 06  Código base de AulaPlus

Este proyecto pequeño representa la arquitectura diseñada en la Unidad 3. Su proceso principal es reserva, pago, cancelación, disputa y liberación de fondos de una tutoría. Usa solo la biblioteca estándar de Python 3.11 o superior. Es código base académico: la implementación de infraestructura real y las políticas aún abiertas se incorporarán cuando el equipo las valide.

## Ejecutar

Desde esta carpeta, en PowerShell:

```powershell
$env:PYTHONPATH = 'src'
python demo.py
python -m unittest discover -s tests -v
```

`demo.py` muestra CU-01 (reserva), CU-02 (confirmación de pago) y una consulta de detalle. Las pruebas cubren rechazo por menos de dos horas, congelamiento de diez minutos, doble reserva, confirmación, vencimiento, lectura y bloqueo de liberación con disputa. El reloj fijo hace reproducibles los escenarios.

## Organización y responsabilidades

| Archivo | Capa | Responsabilidad |
|---|---|---|
| `src/aulaplus/domain.py` | Dominio | `TransaccionSesion` y `AgendaTutor` protegen estados e invariantes; `Dinero` y `VentanaHoraria` son Value Objects; eventos describen hechos ocurridos. |
| `src/aulaplus/services.py` | Aplicación | Los servicios coordinan CU-01 a CU-05. No almacenan condiciones de tiempo, dinero o estado. |
| `src/aulaplus/ports.py` | Contratos | Repository por Aggregate Root, Unit of Work, reloj y lecturas. Ningún método de Repository contiene SQL. |
| `src/aulaplus/cqrs.py` | Aplicación | Dos Commands con handlers y dos Queries con DTOs de lectura propios. |
| `src/aulaplus/memory.py` | Infraestructura | Repositorios y Unit of Work en memoria. Una confirmación guarda las dos raíces y eventos pendientes; ante error, las copias de trabajo se descartan. |
| `tests/test_scenarios.py` | Pruebas | Escenarios seleccionados para verificar reglas y resultado atómico. |

La dirección de dependencias es `services/cqrs → domain + ports` y `memory → domain + ports`. El dominio no conoce Python web, SQL ni la implementación en memoria. Los nombres de clases conservan el glosario de AulaPlus; los métodos usan `snake_case` por convención de Python.

## Trazabilidad mínima

| Caso | Entrada y colaboración | Regla y estado | Resultado |
|---|---|---|---|
| CU-01 | `ServicioReservaSesion.reservar_sesion`; `RepositorioAgendaTutor`, `RepositorioTransaccionSesion`, `UnidadDeTrabajo` | R-02 mínimo 2 h; R-03 congelar 10 min; R-10 agenda reciente | `TransaccionSesion` Reservada y `BloqueDeAgenda` Congelado en un commit. |
| CU-02 | `confirmar_pago_reserva` / `expirar_congelamiento` | R-03/R-04: pago antes de vencer bloquea; sin pago se libera | Confirmada y Bloqueado, o Cancelada y Disponible. |
| CU-03 | `ServicioCancelacionSesion` | R-06: `PoliticaReembolso` inyectada | Cancela y registra reembolso; H-05 requiere política aprobada. |
| CU-04 | `ServicioDisputaSesion` | R-08: una disputa impide liberar | EnRevision y evento `DisputaAbierta`. |
| CU-05 | `ServicioLiquidacionPago` | R-01: 20 % de comisión; R-05: `PoliticaRetencion` inyectada | Comisión y neto tras sesión completada, sin disputa. H-01 no se fija aquí. |

La matriz completa está en `../04_Matriz_de_Trazabilidad_AulaPlus.xlsx`. El diagrama de clases y las secuencias están en los entregables 02 y 03. Los tres ADR se explican en el informe 01: Domain Model, transacción local y CQRS básico.

## Decisiones para el siguiente paso

- **H-01:** la liberación normal aparece como 48 h en el BRD y 72 h en un diseño previo. La mediación de disputa es otro plazo de 72 h. `PoliticaRetencion` exige una elección explícita; no hay valor por defecto.
- **H-05:** el BRD da rangos de reembolso, pero faltan límites exactos y excepciones. `PoliticaReembolso` se inyecta; este repositorio no publica una tabla de porcentajes como regla definitiva.
- **H-06:** falta capacidad y control atómico de sede entre tutores. La reserva presencial se rechaza con `DecisionPendiente`; el ejemplo cubre modalidad en línea.
- **H-11/H-13:** un cobro confirmado tras vencer debe compensarse fuera del commit local; el registro de pago fallido requiere definición. `confirmar_pago_reserva` representa solo un cobro ya confirmado y oportuno.
- **H-15:** la captura y evaluación de evidencia para marcar `Completada` requiere un caso de uso adicional. El método de dominio exige evidencia validada; la prueba lo usa como fixture y no lo presenta como flujo productivo.
- La infraestructura relacional futura necesita control de versiones, transacción ACID y outbox persistente. El bloqueo global de `UnidadDeTrabajoMemoria` solo demuestra atomicidad dentro de este proceso.

## Revisión SOLID en el código

`ServicioReservaSesion` coordina y las raíces validan (S). Reembolso y retención se sustituyen mediante protocolos al aprobar reglas (O, D). Los contratos de repositorio son pequeños y específicos por raíz (I). Las implementaciones pueden cambiar si conservan las mismas respuestas y errores; las pruebas de contrato de una base real están pendientes (L). Ningún `QueryHandler` devuelve una entidad mutable del dominio.

## Alcance de la entrega

La guía permite código parcial o de estructura. Aquí los dos flujos de los diagramas de secuencia son ejecutables; CU-03 a CU-05 tienen servicios y reglas clave, pero dependen de las políticas y evidencia mencionadas arriba. El entregable 07 incorporará el proyecto al repositorio GitHub con historial y enlaces.
