# Documento de decisiones técnicas — AulaPlus

Índice de la arquitectura del PIA. Todo lo descrito aquí existe en `src/` y está probado en `tests/`.

| Documento | Contenido |
|---|---|
| [diagrams/01-modelo-dominio-ddd.md](diagrams/01-modelo-dominio-ddd.md) | Modelo DDD y diagrama de clases (Aggregates, entidades, Value Objects, servicios, eventos, Specifications) |
| [diagrams/02-maquinas-de-estado.md](diagrams/02-maquinas-de-estado.md) | Máquinas de estado de sesión, pago y bloque |
| [diagrams/03-secuencias.md](diagrams/03-secuencias.md) | Secuencias CU-01, CU-02 y CU-05 con las clases reales |
| [diagrams/04-componentes-y-despliegue.md](diagrams/04-componentes-y-despliegue.md) | Capas (hexagonal), dependencias y despliegue Docker/CI/Render |
| [adr/](adr/) | ADR-001 a ADR-007 (contexto, alternativas, decisión, consecuencias) |
| [trazabilidad.md](trazabilidad.md) | BRD → US → regla → BPMN → código → prueba |
| [diferencias-paquete-pia.md](diferencias-paquete-pia.md) | Cómo se adaptó el paquete de datos del PIA sin reemplazar nuestros requisitos |
| [diagrams/u3/](diagrams/u3/) | Diagramas originales de la Unidad 3 (referencia histórica) |

## 1. Estilo arquitectónico

**Arquitectura hexagonal (puertos y adaptadores) con DDD táctico.**

```
api (FastAPI)  ──►  application (casos de uso, CQRS)  ──►  domain (reglas puras)
                         │ puertos (Protocol)
infrastructure (SQLAlchemy, UoW, outbox, config) ──implementa──┘
```

- `src/domain`: no importa FastAPI, SQLAlchemy ni `datetime.now()`. Se prueba en milisegundos.
- `src/application`: un método por caso de uso; abre la Unit of Work, invoca al dominio y confirma.
- `src/infrastructure`: persistencia, lectura CQRS, configuración por entorno, importador del paquete PIA.
- `src/api`: traduce HTTP ⇄ casos de uso y excepciones de dominio ⇄ códigos HTTP. `container.py` es el Composition Root.

## 2. Patrones usados y por qué

| Patrón | Dónde | Problema que resuelve |
|---|---|---|
| Domain Model + Aggregates | `TransaccionSesion`, `AgendaTutor` | Invariantes de tiempo, dinero y estado compartidas por 5 casos de uso (ADR-001) |
| Value Object | `Dinero`, `VentanaHoraria`, `DesgloseFinanciero`, `EvidenciaAsistencia`… | Montos con `Decimal` sin negativos, fechas siempre con zona horaria, comisión + neto = bruto |
| Specification (AND/OR/NOT) | `domain/specifications.py` | Reglas de reserva y liberación con nombre, combinables y con motivo de rechazo |
| State Machine (tabla) | `domain/state_machine.py` | Transiciones válidas en un solo lugar; las 50 inválidas → 409 |
| Domain Events + Outbox | `domain/events.py`, `EventoOutboxRow` | Anunciar solo hechos confirmados (ADR-002) |
| Domain Service / Strategy | `CalculadoraReembolso`, `PoliticaCompensacion`, `PoliticaSuspension` | Políticas que cambian sin tocar los Aggregates |
| Service Layer | `application/services.py` | Coordinación de casos de uso sin reglas de negocio |
| Repository | `infrastructure/repositories.py` | Cargar/guardar Aggregates completos; versión optimista |
| Unit of Work | `infrastructure/unit_of_work.py` | Sesión + agenda + eventos en un solo COMMIT |
| CQRS básico | `application/queries.py`, `infrastructure/lecturas.py` | Lecturas como DTO sin cargar Aggregates (ADR-003) |
| Pessimistic lock | `RepositorioSqlSede.obtener_para_reserva` | Último cupo de sede compartido (ADR-006) |
| Dependency Injection / Composition Root | `api/container.py` | Sustituir infraestructura en pruebas (SQLite, `RelojFijo`) |
| Adapter | `infrastructure/paquete_pia.py` | Ejecutar los CSV del docente sobre nuestro dominio |

## 3. Principios SOLID (demostrables en el código)

| Principio | Evidencia concreta | Cómo se demuestra |
|---|---|---|
| **S** — Responsabilidad única | `ServicioReservaSesion` solo coordina; la regla de 2 h vive en `AnticipacionMinimaSpec`; el mapeo SQL en `RepositorioSqlTransaccionSesion`; los códigos HTTP en `api/main.py` | Cambiar el plazo no toca servicios ni API |
| **O** — Abierto/cerrado | `Specification` se extiende con nuevas clases y se compone con `& \| ~`; políticas inyectadas en `Politicas` | Agregar una regla de reserva = nueva Spec en `reserva_permitida`, sin modificar `TransaccionSesion` |
| **L** — Sustitución de Liskov | Cualquier `UnidadDeTrabajo` (SQLite en memoria, PostgreSQL) y cualquier `Reloj` (`RelojSistema`, `RelojFijo`) son intercambiables | La misma suite pasa con SQLite y con PostgreSQL (199 pruebas en Docker) |
| **I** — Segregación de interfaces | Puertos pequeños por Aggregate (`RepositorioAgendaTutor`, `RepositorioSede`…) y `LecturasAulaPlus` separado de la escritura | Las Queries no ven métodos de escritura |
| **D** — Inversión de dependencias | `application` depende de `ports.py` (Protocol); solo `container.py` instancia clases concretas | Las pruebas inyectan `RelojFijo` y SQLite en memoria sin cambiar código |

## 4. Decisiones técnicas transversales

- **Dinero:** `Decimal` con `ROUND_HALF_UP` a centavos; en la base se guarda en **centavos enteros**.
- **Tiempo:** UTC con zona horaria obligatoria (`DatoInvalido` si falta). El dominio recibe `ahora` como parámetro.
- **Errores → HTTP:** `DatoInvalido` 400 · `RecursoNoEncontrado` 404 · `TransicionInvalida`/`ConflictoDeRecurso` 409 ·
  `ReglaDeNegocioViolada` 422 · validación de esquema 422. Cuerpo: `{"codigo", "mensaje"}`.
- **Orden en cada comando:** validar → cambiar estado → registrar evento. Si algo falla, el Aggregate queda intacto y
  la UoW hace ROLLBACK (probado).
- **Concurrencia:** optimista por `version` (agenda y sesión) + pesimista por sede (`FOR UPDATE`).
- **Configuración 12-Factor:** `infrastructure/config.py` lee variables de entorno; `.env.example` sin secretos.
- **Demo de plazos:** cabecera `X-Fecha-Simulada`, solo si `PERMITIR_FECHA_SIMULADA=true` (desactivar en producción real).
- **Esquema de base:** `create_all` al iniciar (suficiente para el PIA). Evolución futura: Alembic.

## 5. Riesgos y límites conocidos

- US-10, US-12 y US-13 están en backlog (ver trazabilidad).
- El outbox se llena pero no hay *relay* a un broker de mensajería.
- Sin autenticación: los IDs de estudiante/tutor llegan en el cuerpo. En producción se tomarían del token (RBAC de U5).
- SQLite no soporta `FOR UPDATE`: las pruebas de concurrencia corren solo contra PostgreSQL (Docker y CI).
