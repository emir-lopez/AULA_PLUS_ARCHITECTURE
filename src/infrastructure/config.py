"""Configuración 12-Factor: todo valor que cambia entre entornos llega por variables de entorno."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from domain.policies import ParametrosOperacion, PoliticaSuspension


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./aulaplus.db"
    seed_demo: bool = False
    permitir_fecha_simulada: bool = False
    log_level: str = "info"

    # Parámetros de negocio confirmados en el BRD (ver ADR-004).
    minutos_congelamiento: int = 10
    horas_retencion: int = 48
    horas_mediacion: int = 72
    minutos_tolerancia_no_show: int = 10
    horas_anticipacion_minima: int = 2
    dias_vigencia_agenda: int = 7
    marcas_para_suspension: int = 3
    minutos_tolerancia_conexion: int = 15
    minutos_maximos_extension: int = 60

    def parametros(self) -> ParametrosOperacion:
        return ParametrosOperacion(
            minutos_congelamiento=self.minutos_congelamiento,
            horas_retencion=self.horas_retencion,
            horas_mediacion=self.horas_mediacion,
            minutos_tolerancia_no_show=self.minutos_tolerancia_no_show,
            horas_anticipacion_minima=self.horas_anticipacion_minima,
            dias_vigencia_agenda=self.dias_vigencia_agenda,
            minutos_tolerancia_conexion=self.minutos_tolerancia_conexion,
            minutos_maximos_extension=self.minutos_maximos_extension,
        )

    def politica_suspension(self) -> PoliticaSuspension:
        return PoliticaSuspension(self.marcas_para_suspension)

    @property
    def url_normalizada(self) -> str:
        # Render/Railway entregan "postgres://"; SQLAlchemy 2 + psycopg 3 requieren "postgresql+psycopg://".
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
