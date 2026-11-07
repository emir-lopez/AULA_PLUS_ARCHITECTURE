# API REST — contrato OpenAPI

- Especificación: [`openapi.json`](openapi.json) (OpenAPI 3.1, generada desde el código con `python scripts/exportar_openapi.py`).
- Swagger UI: `http://localhost:8000/docs` (local / Docker) y `https://<servicio>.onrender.com/docs` (producción).
- ReDoc: `/redoc`. Salud: `GET /health`.

## Endpoints

| Método | Ruta | Caso de uso | Éxito | Errores típicos |
|---|---|---|---|---|
| POST | `/tutores` | Registrar tutor | 201 | 409 TutorDuplicado, 422 |
| POST | `/tutores/{id}/bloques` | Publicar disponibilidad | 201 | 400 VentanaInvalida, 404, 409 BloqueEmpalmado |
| POST | `/sedes` | Registrar sede | 201 | 409 SedeDuplicada |
| GET | `/tutores/disponibles?inicio&fin` | US-11 Buscar | 200 | 400 |
| POST | `/sesiones` | CU-01 Reservar | 201 | 404, 409 SesionDuplicada, 422 AnticipacionInsuficiente / HorarioNoDisponible / SinCupoEnSede / PerfilNoVisible / TutorSuspendido |
| POST | `/sesiones/{id}/pago` | CU-02 Pago (Confirmado/Fallido) | 200 | 409 TransicionInvalida, 422 MontoDePagoIncorrecto / CongelamientoVencido |
| POST | `/sesiones/{id}/expirar` | CU-02 Vencimiento | 200 | 404 |
| POST | `/sesiones/{id}/cancelacion-estudiante` | CU-03 | 200 | 409, 422 SesionYaInicio |
| POST | `/sesiones/{id}/cancelacion-tutor` | US-08 | 200 | 409, 422 |
| POST | `/sesiones/{id}/completar` | US-04/05/06/19 | 200 | 409, 422 SesionNoFinalizada |
| POST | `/sesiones/{id}/no-show` | US-15 | 200 | 409, 422 ToleranciaNoCumplida |
| POST | `/sesiones/{id}/calificacion` | US-18 | 200 | 422 SesionYaCalificada |
| POST | `/sesiones/{id}/disputa` | CU-04 | 200 | 409, 422 VentanaDeDisputaCerrada / DisputaYaAbierta |
| POST | `/sesiones/{id}/resolucion` | Mediación de Soporte | 200 | 400, 409 |
| POST | `/sesiones/{id}/liberacion` | CU-05 | 200 | 422 RetencionVigente / DisputaAbierta |
| GET | `/sesiones/{id}` · `/sesiones/{id}/eventos` | Detalle / Domain Events | 200 | 404 |
| GET | `/soporte/disputas` · `/liquidaciones/pendientes` · `/indicadores` | Consultas CQRS y KPIs | 200 | — |

Formato de error para todo error de dominio: `{"codigo": "MontoDePagoIncorrecto", "mensaje": "Se esperaba 350.00 MXN y se recibió 1.00 MXN"}`.
