"""Ejecuta casos_prueba.csv (120) y transiciones_prueba.csv (20) y guarda resultado + evidencia."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from infrastructure.paquete_pia import ejecutar_casos, ejecutar_transiciones, escribir_resultados  # noqa: E402

paquete = RAIZ / "tests" / "data" / "paquete_pia"
salida = RAIZ / "docs" / "evidencias"
casos, transiciones = ejecutar_casos(paquete), ejecutar_transiciones(paquete)
escribir_resultados(salida / "resultados_casos_prueba.csv", casos)
escribir_resultados(salida / "resultados_transiciones_prueba.csv", transiciones)
print(f"{len(casos)} casos y {len(transiciones)} transiciones -> {salida}")
