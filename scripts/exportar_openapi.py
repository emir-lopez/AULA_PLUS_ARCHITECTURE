"""Exporta el contrato OpenAPI de la API a docs/api/openapi.json (o a la ruta indicada)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.main import create_app  # noqa: E402
from infrastructure.config import Settings  # noqa: E402

destino = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/api/openapi.json")
destino.parent.mkdir(parents=True, exist_ok=True)
esquema = create_app(Settings(database_url="sqlite://")).openapi()
destino.write_text(json.dumps(esquema, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OpenAPI {esquema['info']['version']}: {len(esquema['paths'])} rutas -> {destino}")
