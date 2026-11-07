# ---------------------------------------------------------------------------
# AulaPlus - imagen multi-stage
#   base    : Python + dependencias de ejecución (capa cacheable)
#   test    : base + dependencias de desarrollo + tests (la usa el servicio "tests")
#   runtime : imagen de producción (usuario sin privilegios, healthcheck).
#             Es la ÚLTIMA etapa: `docker build .` y Render construyen esta por defecto.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# ------------------------------------------------------------------- test
FROM base AS test

COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY pyproject.toml ./
COPY src ./src
COPY tests ./tests

CMD ["sh", "-c", "mkdir -p reports && pytest --cov --cov-report=term-missing --cov-report=xml:reports/coverage.xml --junitxml=reports/junit.xml --cov-fail-under=80"]

# ---------------------------------------------------------------- runtime
FROM base AS runtime

COPY src ./src
RUN useradd --create-home --uid 10001 aulaplus && chown -R aulaplus /app
USER aulaplus

ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4)" || exit 1

# sh -c para expandir $PORT (Render/Railway/Fly lo inyectan); exec para que uvicorn reciba las señales.
CMD ["sh", "-c", "exec uvicorn api.main:app --app-dir src --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips=*"]
