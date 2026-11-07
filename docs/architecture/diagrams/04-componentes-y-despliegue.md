# Arquitectura de componentes (hexagonal) y despliegue

## Capas y dirección de dependencias

```mermaid
flowchart TB
  subgraph API["src/api (adaptador de entrada)"]
    R[routes.py<br/>FastAPI endpoints]
    M[main.py<br/>errores → HTTP, X-Fecha-Simulada, /health]
    C[container.py<br/>Composition Root]
  end
  subgraph APP["src/application"]
    SV[services.py<br/>ServicioReserva / Cancelacion / Ejecucion / Disputa / Liquidacion / Agenda]
    QY[queries.py<br/>ConsultasAulaPlus]
    PT[ports.py<br/>Repositorios, UnidadDeTrabajo, Reloj, Lecturas]
  end
  subgraph DOM["src/domain (sin dependencias externas)"]
    AG[Aggregates<br/>TransaccionSesion · AgendaTutor]
    VO[Value Objects]
    SP[Specifications]
    SM[State Machine]
    EV[Domain Events]
    PO[Políticas / Domain Services]
  end
  subgraph INF["src/infrastructure (adaptadores de salida)"]
    RP[repositories.py<br/>SQLAlchemy + versión]
    UW[unit_of_work.py<br/>COMMIT + outbox]
    LE[lecturas.py<br/>CQRS read model]
    CF[config.py<br/>variables de entorno]
    PQ[paquete_pia.py<br/>importador CSV]
  end
  DB[("PostgreSQL 16")]

  R --> SV
  R --> QY
  C --> SV & QY & RP & UW & LE & CF
  SV --> PT
  SV --> AG
  QY --> PT
  AG --> VO & SP & SM & EV & PO
  RP -. implementa .-> PT
  UW -. implementa .-> PT
  LE -. implementa .-> PT
  RP & UW & LE --> DB
```

`domain` no importa nada de `application`, `infrastructure` ni `api`. `application` depende solo de `domain` y de sus
puertos. Solo `api/container.py` conoce las clases concretas (DIP).

## Despliegue

```mermaid
flowchart LR
  subgraph Local["docker compose (local / CI)"]
    db[("db<br/>postgres:16-alpine<br/>healthcheck pg_isready<br/>volumen pgdata")]
    app[app<br/>imagen runtime<br/>usuario sin root<br/>HEALTHCHECK /health :8000]
    tests["tests (profile test)<br/>imagen test<br/>pytest + cobertura ≥80 %"]
    app -- DATABASE_URL --> db
    tests -- TEST_DATABASE_URL<br/>base aulaplus_test --> db
  end
  subgraph GH["GitHub Actions"]
    j1[calidad: ruff + pytest + PG de servicio] --> j2[docker: compose build/up/tests] --> j3[deploy: hook de Render]
  end
  subgraph Render["Render (render.yaml)"]
    web[Web Service Docker<br/>/docs Swagger]
    pg[("Render PostgreSQL")]
    web --> pg
  end
  j3 --> web
```
