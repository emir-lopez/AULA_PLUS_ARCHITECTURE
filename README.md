# AulaPlus · PIA Componentes de Lógica de Negocio

Plataforma de tutorías que conecta **estudiantes** y **tutores** (presencial o en línea) y retiene una **comisión del
20 %** por sesión. Implementación del Producto Integrador de Aprendizaje con **DDD, Specification, State Machine,
Domain Events, API REST (FastAPI + OpenAPI), PostgreSQL, pruebas ≥ 80 %, Docker Compose y CI/CD**.

- **Caso:** 08 — AulaPlus · FIME, UANL · Prof. Miguel Ángel Gómez Marroquín
- **Equipo 8:** Andrés Caleb Leija Pedroza (2144830) · David Alonso Torres Guerrero (2144813) · Emir Misael López Pérez (2150561)
- **Repositorio:** https://github.com/emir-lopez/AULA_PLUS_ARCHITECTURE
- **Sistema desplegado (Swagger):** `https://<servicio>.onrender.com/docs` ← *anotar la URL después de desplegar*

| Indicador | Resultado |
|---|---|
| Pruebas | 199 (unitarias + integración + PostgreSQL real) — todas en verde |
| Cobertura | 98.6 % líneas y ramas (mínimo exigido 80 %) |
| Historias de usuario | 19 con Gherkin (16 implementadas y probadas, 3 en backlog documentado) |
| Paquete del PIA | 120 casos + 20 transiciones ejecutados por el dominio ([evidencia](docs/evidencias/)) |

---

## 1. Ejecución rápida con Docker (recomendado)

Requisitos: Docker Desktop (Windows/macOS) o Docker Engine + Compose v2.

```bash
cp .env.example .env                      # opcional: ajustar contraseñas y parámetros
docker compose up -d --build              # db (PostgreSQL 16) + app
# Swagger UI:  http://localhost:8000/docs
# Salud:       http://localhost:8000/health

docker compose --profile test run --rm tests   # suite completa contra PostgreSQL (reportes en ./reports)
docker compose logs -f app                     # ver logs
docker compose down -v                         # detener y borrar datos
```

| Servicio | Imagen | Función |
|---|---|---|
| `db` | `postgres:16-alpine` | Base de datos con volumen `pgdata` y healthcheck `pg_isready`. Crea también `aulaplus_test` |
| `app` | etapa `runtime` del Dockerfile | API FastAPI con usuario sin root y HEALTHCHECK a `/health`; espera a que `db` esté sana |
| `tests` | etapa `test` (perfil `test`) | pytest + cobertura ≥ 80 % contra PostgreSQL; escribe `reports/coverage.xml` y `junit.xml` |

> **Windows + OneDrive:** si `docker compose build` muestra `additional privileges requested: --allow=fs.read`,
> ejecuta el comando desde la ruta con las mayúsculas reales (`C:\Users\<usuario>\OneDrive\Documentos\...`).
> Es un problema de Compose v5 con las carpetas de OneDrive (puntos de reparación), no del proyecto.

## 2. Ejecución local sin Docker

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    ·    Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                       # usa SQLite por defecto
uvicorn api.main:app --app-dir src --reload
```

## 3. Pruebas y calidad

```bash
pytest                                              # 196 pruebas (las 3 de PostgreSQL se omiten sin BD)
pytest --cov --cov-report=term-missing --cov-fail-under=80
ruff check src tests scripts
TEST_DATABASE_URL=postgresql+psycopg://aulaplus:aulaplus_local@localhost:5432/aulaplus_test pytest   # con el db de compose
python scripts/ejecutar_paquete_pia.py              # regenera docs/evidencias/*.csv (120 casos + 20 transiciones)
python scripts/exportar_openapi.py                  # regenera docs/api/openapi.json
```

| Carpeta | Qué prueba |
|---|---|
| `tests/unit/` | Value Objects, políticas (reembolso con fronteras 24 h / 6 h), Specifications AND/OR/NOT, matriz completa de la máquina de estados (6 × 10), Aggregates |
| `tests/integration/test_servicios_sql.py` | Casos de uso con SQLAlchemy: atomicidad, rollback, outbox, conflicto de versión, cupo de sede, flujo completo y KPIs |
| `tests/integration/test_api.py` | Contrato HTTP: 200/201, 400, 404, 409, 422, Swagger y cabecera `X-Fecha-Simulada` |
| `tests/integration/test_paquete_pia.py` | Los CSV del docente: claves foráneas, totales con `Decimal`, 120 casos y 20 transiciones |
| `tests/integration/test_postgres.py` | PostgreSQL real: zona horaria, 5 reservas concurrentes del mismo bloque, último cupo de sede entre tres tutores |

## 4. CI/CD

`.github/workflows/ci.yml` se ejecuta en cada push y pull request:

1. **calidad**: Ruff → pytest con cobertura ≥ 80 % (con PostgreSQL de servicio) → exporta OpenAPI → sube reportes.
2. **docker**: `docker compose build` → `up --wait` (healthchecks) → `curl /health` y `/docs` → `run tests`.
3. **deploy** (solo `main`): dispara el *deploy hook* de Render si existe el secreto `RENDER_DEPLOY_HOOK_URL`.

## 5. Despliegue en Render

1. En Render: **New → Blueprint** → seleccionar este repositorio. `render.yaml` crea `aulaplus-db` (PostgreSQL) y
   `aulaplus-api` (Docker, healthcheck `/health`).
2. Esperar al primer deploy y abrir `https://aulaplus-api-xxxx.onrender.com/docs`.
3. (Opcional) Copiar el *Deploy Hook* del servicio a GitHub → Settings → Secrets → `RENDER_DEPLOY_HOOK_URL`.
4. Anotar la URL arriba en este README.

La URL `postgres://` de Render se normaliza automáticamente; el puerto se toma de `$PORT` (12-Factor).

## 6. Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./aulaplus.db` | Conexión (en compose apunta a `db`) |
| `APP_ENV` | `development` | Etiqueta del entorno (`/health`) |
| `SEED_DEMO` | `false` | Carga 3 tutores, 60 bloques y 2 sedes ficticios |
| `PERMITIR_FECHA_SIMULADA` | `false` | Habilita la cabecera `X-Fecha-Simulada` para la demo |
| `MINUTOS_CONGELAMIENTO` · `HORAS_RETENCION` · `HORAS_MEDIACION` · `MINUTOS_TOLERANCIA_NO_SHOW` · `HORAS_ANTICIPACION_MINIMA` · `DIAS_VIGENCIA_AGENDA` · `MARCAS_PARA_SUSPENSION` | 10 · 48 · 72 · 10 · 2 · 7 · 3 | Parámetros de negocio del BRD |
| `POSTGRES_USER` · `POSTGRES_PASSWORD` · `POSTGRES_DB` · `APP_PORT` · `DB_PORT` | ver `.env.example` | Docker Compose |

## 7. Estructura

```
docs/
  BRD.md · user-stories.md (19 US + Gherkin) · bpmn.md · glosario.md (33 términos)
  architecture/  README (decisiones técnicas, patrones, SOLID) · adr/ (7 ADR) · diagrams/ · trazabilidad.md
  api/           openapi.json · README
  evidencias/    resultados de los 120 casos y 20 transiciones del paquete PIA
  legacy-u3/     entregables de la Unidad 3
src/
  domain/          Aggregates, Value Objects, Specifications, State Machine, Domain Events, políticas
  application/     Application Services (casos de uso), Queries CQRS, puertos
  infrastructure/  SQLAlchemy, repositorios, Unit of Work + outbox, lecturas, config, importador del paquete PIA
  api/             FastAPI: endpoints, esquemas, manejo de errores, Composition Root
tests/             unit/ · integration/ · data/paquete_pia/
scripts/           exportar_openapi.py · ejecutar_paquete_pia.py
.github/workflows/ci.yml · Dockerfile · docker-compose.yml · render.yaml · .env.example
```

## 8. Guion de la demo en vivo (Swagger, ~8 min)

Con `SEED_DEMO=true` y `PERMITIR_FECHA_SIMULADA=true`. Para los pasos con plazos, agrega la cabecera
`X-Fecha-Simulada` en Swagger o usa `curl -H "X-Fecha-Simulada: 2026-11-21T17:05:00Z"`.

1. `GET /health` → PostgreSQL conectado.
2. `GET /tutores/disponibles` (mañana 16:00–17:00) → elegir `tutor_id` y `bloque_id`.
3. `POST /sesiones` → **201** Reservada, `congelado_hasta` = ahora + 10 min (US-02).
4. `POST /sesiones/{id}/pago` con monto incorrecto → **422** `MontoDePagoIncorrecto`; con el correcto → **200** Confirmada (US-03).
5. Repetir el pago → **409** `TransicionInvalida` (State Machine).
6. `POST /sesiones` con el mismo bloque → **422** `HorarioNoDisponible`. `GET /sesiones/NO` → **404**.
7. `POST /completar` con evidencia y `X-Fecha-Simulada` = fin de la sesión → Completada, comisión 70.00 y neto 280.00 (US-19).
8. `POST /liberacion` a +1 h → **422** `RetencionVigente`; a +48 h → **200** pago Liberado (US-17).
9. `GET /sesiones/{id}/eventos` → Domain Events del outbox. `GET /indicadores` → KPIs del BRD.
10. Extra: disputa (`/disputa` → `/soporte/disputas` → `/resolucion`), cancelación con reembolso del 50 %, No-Show.

## 9. Trazabilidad

La [matriz de trazabilidad](docs/architecture/trazabilidad.md) relaciona cada regla del BRD (R-01…R-16) con su
historia, paso del BPMN, clase, endpoint y prueba. Las diferencias con el paquete de datos del docente están en
[diferencias-paquete-pia.md](docs/architecture/diferencias-paquete-pia.md).
