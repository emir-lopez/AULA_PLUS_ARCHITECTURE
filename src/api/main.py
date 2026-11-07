"""Punto de entrada FastAPI. Swagger UI en /docs y contrato OpenAPI en /openapi.json.

Ejecutar:  uvicorn api.main:app --app-dir src --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text

from domain.exceptions import (
    ConflictoDeRecurso,
    DatoInvalido,
    ErrorDeDominio,
    RecursoNoEncontrado,
    ReglaDeNegocioViolada,
    TransicionInvalida,
)
from infrastructure.clock import RelojSistema
from infrastructure.config import Settings, get_settings
from infrastructure.seed import sembrar

from .container import Contenedor, construir_contenedor
from .routes import router

ESTADO_HTTP: list[tuple[type[ErrorDeDominio], int]] = [
    (DatoInvalido, 400),
    (RecursoNoEncontrado, 404),
    (TransicionInvalida, 409),
    (ConflictoDeRecurso, 409),
    (ReglaDeNegocioViolada, 422),
]

DESCRIPCION = """
API de **AulaPlus** (Caso 08, Equipo 8 — Componentes de Lógica de Negocio, FIME UANL).

Proceso principal: **reservar → pagar → impartir → completar → (disputa) → liberar pago al tutor**.

* Errores de dominio: `400` dato inválido · `404` no encontrado · `409` transición inválida o conflicto ·
  `422` regla de negocio violada. Cuerpo: `{"codigo": "...", "mensaje": "..."}`.
* Demo: si `PERMITIR_FECHA_SIMULADA=true`, la cabecera `X-Fecha-Simulada` (ISO-8601 con zona)
  fija la hora de la petición para demostrar plazos de 10 min, 48 h y 72 h.
"""


def create_app(settings: Settings | None = None, contenedor: Contenedor | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.contenedor is None:
            app.state.contenedor = construir_contenedor(settings)
        if settings.seed_demo:
            sembrar(app.state.contenedor.agenda, app.state.contenedor.reloj.ahora())
        yield

    app = FastAPI(title="AulaPlus API", version="1.0.0", description=DESCRIPCION, lifespan=lifespan)
    app.state.contenedor = contenedor
    app.state.settings = settings

    @app.middleware("http")
    async def fecha_simulada(request: Request, call_next):
        cabecera = request.headers.get("X-Fecha-Simulada")
        if not (cabecera and settings.permitir_fecha_simulada):
            return await call_next(request)
        try:
            valor = datetime.fromisoformat(cabecera.replace("Z", "+00:00"))
            if valor.tzinfo is None:
                raise ValueError
        except ValueError:
            return JSONResponse(status_code=400, content={"codigo": "FechaSimuladaInvalida",
                                                          "mensaje": "Use ISO-8601 con zona horaria"})
        token = RelojSistema.simular(valor)
        try:
            return await call_next(request)
        finally:
            RelojSistema.restaurar(token)

    @app.exception_handler(ErrorDeDominio)
    async def manejar_dominio(_: Request, exc: ErrorDeDominio) -> JSONResponse:
        codigo_http = next((http for tipo, http in ESTADO_HTTP if isinstance(exc, tipo)), 400)
        return JSONResponse(status_code=codigo_http, content={"codigo": exc.codigo, "mensaje": exc.mensaje})

    @app.get("/", include_in_schema=False)
    def raiz() -> RedirectResponse:
        return RedirectResponse("/docs")

    @app.get("/health", tags=["operación"], summary="Liveness/readiness: verifica la conexión a la DB")
    def health(request: Request) -> dict:
        c: Contenedor = request.app.state.contenedor
        with c.consultas.lecturas.fabrica() as s:
            s.execute(text("SELECT 1"))
        return {"status": "ok", "env": settings.app_env,
                "database": settings.url_normalizada.split(":", 1)[0]}

    app.include_router(router)
    return app


app = create_app()
