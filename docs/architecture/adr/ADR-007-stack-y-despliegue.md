# ADR-007 · Stack, contenedores y despliegue

- **Estado:** Aceptada
- **Decisión:** Python 3.12 · FastAPI (OpenAPI/Swagger automático) · SQLAlchemy 2 + psycopg 3 · PostgreSQL 16 ·
  pytest + pytest-cov · Ruff · Docker multi-stage (`runtime` sin root y con HEALTHCHECK, `test` con la suite) ·
  Docker Compose (db + app + tests) · GitHub Actions · Render (Blueprint `render.yaml`).
- **Por qué:** continuidad con U4 (FastAPI) y U5 (pytest, SQLAlchemy, Actions). El dominio no depende de ninguna de
  estas piezas (DIP): cambiar FastAPI o la base solo afecta `api/` o `infrastructure/`.
- **12-Factor:** toda la configuración llega por variables de entorno (`infrastructure/config.py`, `.env.example`);
  la URL `postgres://` que entregan Render/Railway se normaliza a `postgresql+psycopg://`; el puerto se toma de `$PORT`.
- **Alternativas descartadas:** Django (más acoplamiento entre ORM y dominio); SQLite en producción (sin concurrencia
  real ni `FOR UPDATE`).
- **Consecuencias:** entorno reproducible con un comando; las pruebas de concurrencia requieren PostgreSQL.
