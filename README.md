# AulaPlus · Arquitectura de Lógica de Negocio

Diseño arquitectónico y código base académico de **AulaPlus**, una plataforma que conecta estudiantes y tutores para sesiones presenciales o en línea y cobra una comisión por sesión.

Proyecto de la **Unidad 3** del curso **Componentes de Lógica de Negocio** — Facultad de Ingeniería Mecánica y Eléctrica (FIME), UANL.

- **Empresa asignada:** AulaPlus — **Caso 08**
- **Profesor:** Miguel Ángel Gómez Marroquín
- **Equipo 8:**
  - Andrés Caleb Leija Pedroza — 2144830
  - Emir Misael López Pérez — 2150561
  - David Alonso Torres Guerrero — 2144813

> Es un trabajo de diseño y código de estructura. No representa una implementación productiva, y las reglas de negocio que las fuentes no cierran se dejan marcadas como hallazgos (ver [Decisiones pendientes](#decisiones-pendientes)).

---

## Nota sobre el Código Base y Stack Tecnológico (Alcance Unidad 3)

> **Alcance del código.** Conforme a las reglas generales de la actividad —*organizar las reglas y responsabilidades del sistema antes de programarlo por completo* y entregar *código parcial o boilerplate*—, el código incluido en `src/` y `tests/` está escrito en **Python** únicamente con fines de **modelado arquitectónico y validación de responsabilidades**. Es un **prototipo conceptual / referencia ejecutable**, no la implementación final del sistema.
>
> **Propósito en esta entrega.** Demostrar de forma ejecutable:
>
> - La separación entre las capas de **Dominio**, **Aplicación** e **Infraestructura**.
> - El uso estricto del **Lenguaje Ubicuo** del glosario (los nombres de clases conservan los términos de AulaPlus).
> - La protección de invariantes en los Aggregates `TransaccionSesion` y `AgendaTutor`.
> - El diseño de la **Service Layer**, los **Repositories**, la **Unit of Work** y **CQRS**.
>
> **Stack definitivo por definir.** El lenguaje de programación, los frameworks y el motor de base de datos para la construcción final **aún no están definidos**. Esto es viable sin alterar las reglas de negocio porque la arquitectura propuesta es **agnóstica a la tecnología** e independiente de los detalles de infraestructura: el dominio y la aplicación dependen de interfaces (puertos), no de implementaciones concretas (**Principio de Inversión de Dependencias**). Hoy la infraestructura es solo una implementación en memoria (`memory.py`) que puede sustituirse por una relacional u otra sin modificar el dominio.

---

## Proceso modelado

**Reserva → confirmación de pago → cancelación → disputa → liberación de fondos al tutor.**

Casos de uso cubiertos:

| ID | Caso de uso | Actor |
|---|---|---|
| CU-01 | Reservar sesión | Estudiante |
| CU-02 | Confirmar pago de la reserva (o vencer el congelamiento de 10 min) | Sistema de pago / temporizador |
| CU-03 | Cancelar sesión por el estudiante | Estudiante |
| CU-04 | Abrir disputa sobre una sesión | Estudiante / Tutor |
| CU-05 | Liberar pago al tutor | Plataforma (por tiempo) |

## Decisiones de arquitectura

| ADR | Decisión |
|---|---|
| 001 | **Domain Model** para el núcleo transaccional, con dos Aggregate Roots: `TransaccionSesion` y `AgendaTutor`. |
| 002 | **Unit of Work** local con publicación posterior de eventos (outbox, reintentos idempotentes). El cobro externo queda fuera de la transacción. |
| 003 | **CQRS básico** sin bases de datos duplicadas: Commands con handlers y Queries que devuelven DTOs. |

Además se aplicó una revisión **SOLID** con cinco hallazgos (S-01, O-02, L-03, I-04, D-05), documentada en el informe.

## Estructura del repositorio

```
AULA_PLUS_ARCHITECTURE/
├── docs/        # Informe, matriz de trazabilidad y bitácora de IA
├── diagrams/    # Dominio y clases, secuencias CU-01 y CU-02
├── src/         # Código base (Python, prototipo conceptual)
│   └── aulaplus/
├── tests/       # Pruebas de escenarios
├── demo.py
├── terminal.py
├── pyproject.toml
└── README.md
```

## Enlaces a los entregables

| Entregable | Archivo | Contenido |
|---|---|---|
| 01 | [`docs/Reporte_Arquitectura_Negocio_AulaPlus_Unidad_3_Equipo_8.pdf`](docs/Reporte_Arquitectura_Negocio_AulaPlus_Unidad_3_Equipo_8.pdf) | Informe de arquitectura: etapas 1 a 9, patrones, dominio, Service Layer, Repository/UoW, CQRS, SOLID, ADR y validación. |
| 02 | [`diagrams/02_Diagrama_Dominio_y_Clases_AulaPlus.pdf`](diagrams/02_Diagrama_Dominio_y_Clases_AulaPlus.pdf) | Mapa de dominio, diagramas de clases (dominio, aplicación e infraestructura), fichas de Aggregate y glosario. |
| 03 | [`diagrams/03_CU01_Reserva_AulaPlus.pdf`](diagrams/03_CU01_Reserva_AulaPlus.pdf) | Diagrama de secuencia de CU-01: flujo principal y rechazo. |
| 03 | [`diagrams/03_CU02_Pago_y_Vencimiento_AulaPlus.pdf`](diagrams/03_CU02_Pago_y_Vencimiento_AulaPlus.pdf) | Diagrama de secuencia de CU-02: pago oportuno, fallo de pago y vencimiento. |
| 04 | [`docs/04_Matriz_de_Trazabilidad_AulaPlus.pdf`](docs/04_Matriz_de_Trazabilidad_AulaPlus.pdf) | Trazabilidad entre necesidades (BRD), requerimientos, historias, reglas, componentes, persistencia y ADR. |
| 05 | [`docs/05_Bitacora_de_IA_AulaPlus.pdf`](docs/05_Bitacora_de_IA_AulaPlus.pdf) | Bitácora del uso de IA: qué se pidió, qué se corrigió y qué sigue pendiente de validar. |
| 06 | [`src/`](src/) y [`tests/`](tests/) | Código base en Python (ver abajo). |

## Código base (`src/` y `tests/`)

Proyecto pequeño en **Python 3.11+** que usa solo la biblioteca estándar.

| Archivo | Capa | Responsabilidad |
|---|---|---|
| `src/aulaplus/domain.py` | Dominio | Aggregates `TransaccionSesion` y `AgendaTutor`, Value Objects (`Dinero`, `VentanaHoraria`) y eventos de dominio. |
| `src/aulaplus/services.py` | Aplicación | Application Services que coordinan CU-01 a CU-05 sin almacenar reglas de tiempo, dinero o estado. |
| `src/aulaplus/ports.py` | Contratos | Interfaces de Repository por Aggregate Root, Unit of Work, reloj y lecturas. Sin SQL. |
| `src/aulaplus/cqrs.py` | Aplicación | Commands con handlers y Queries con DTOs de lectura propios. |
| `src/aulaplus/memory.py` | Infraestructura | Repositorios y Unit of Work en memoria. |
| `tests/test_scenarios.py` | Pruebas | Escenarios que verifican reglas y resultado atómico. |
| `demo.py` / `terminal.py` | Ejemplos | Demo de CU-01, CU-02 y una consulta; menú de práctica por terminal (pago simulado). |

Dirección de dependencias: `services` / `cqrs` → `domain` + `ports`; `memory` → `domain` + `ports`. El dominio no conoce SQL ni la infraestructura.

### Instrucciones de revisión y ejecución

Desde la raíz del repositorio:

**PowerShell (Windows)**

```powershell
$env:PYTHONPATH = 'src'
python demo.py
python -m unittest discover -s tests -v
```

**Bash (Linux / macOS)**

```bash
export PYTHONPATH=src
python3 demo.py
python3 -m unittest discover -s tests -v
```

Menú interactivo (los datos viven en memoria durante la ejecución):

```bash
python terminal.py
```

Para revisar el diseño, el orden sugerido es: informe (`docs/`) → diagramas (`diagrams/`) → matriz de trazabilidad → código (`src/`) → pruebas (`tests/`).

### Qué cubren las pruebas

Rechazo por menos de dos horas de anticipación, congelamiento de diez minutos, doble reserva del mismo bloque, confirmación de pago, vencimiento del congelamiento, lectura de detalle y bloqueo de liberación de fondos con disputa abierta. Un reloj fijo hace los escenarios reproducibles.

## Decisiones pendientes

Estos puntos no están cerrados por las fuentes del proyecto, así que el diseño y el código **no los dan por resueltos**:

| ID | Tema | Estado |
|---|---|---|
| H-01 | Retención de fondos: 48 h (BRD/entrevista) frente a 72 h (diseño previo); la mediación de disputas es un plazo aparte de 72 h. | `PoliticaRetencion` exige elección explícita. |
| H-05 | Política de reembolso: faltan límites exactos y excepciones de los rangos del BRD. | `PoliticaReembolso` se inyecta. |
| H-06 | Cupo de sede presencial: falta capacidad y control atómico entre tutores. | La reserva presencial devuelve `DecisionPendiente`. |
| H-11 / H-13 | Pago confirmado tras vencer el congelamiento y registro del pago fallido. | Sin regla definida. |
| H-15 | Quién registra la transición a sesión `Completada` (captura de evidencia). | Requiere un caso de uso adicional. |

Una infraestructura relacional real necesitaría control de versiones, transacciones ACID y outbox persistente; el bloqueo de `UnidadDeTrabajoMemoria` solo demuestra atomicidad dentro de un proceso.

## Referencias

- Evans, E. (2003). *Domain-driven design: Tackling complexity in the heart of software*. Addison-Wesley.
- Fowler, M. (2002). *Patterns of enterprise application architecture*. Addison-Wesley.
- Martin, R. C. (2003). *Agile software development: Principles, patterns, and practices*. Prentice Hall.
