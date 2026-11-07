# Modelo de dominio DDD y diagrama de clases (implementación PIA)

Coincide con `src/domain/`. Composición (`*--`) = entidad interna de la raíz; las raíces se referencian solo por ID.

```mermaid
classDiagram
  direction LR

  class TransaccionSesion {
    <<Aggregate Root>>
    +sesion_id
    +estudiante_id
    +tutor_id
    +bloque_id
    +ventana: VentanaHoraria
    +modalidad: Modalidad
    +monto: Dinero
    +congelado_hasta
    +estado: EstadoSesion
    +estado_pago: EstadoPago
    +version
    +reservar(...)$ TransaccionSesion
    +confirmar_pago(monto, ahora)
    +registrar_pago_fallido(motivo, ahora)
    +expirar_congelamiento(ahora) bool
    +cancelar_por_estudiante(id, ahora, calculadora) Dinero
    +cancelar_por_tutor(id, ahora, compensacion)
    +completar_con_evidencia(evidencia, ahora)
    +registrar_no_show(parte, ahora, params, compensacion)
    +abrir_disputa(id, motivo, ahora, params)
    +resolver_revision(a_favor_de, resolucion, ahora)
    +liberar_fondos(ahora, params) DesgloseFinanciero
    +calificar(id, calificacion, ahora)
  }
  class Disputa {
    <<Entity>>
    +motivo
    +abierta_por
    +abierta_en
    +fecha_limite
    +resolucion
    +abierta() bool
  }
  class AgendaTutor {
    <<Aggregate Root>>
    +tutor_id
    +tarifa_hora
    +actualizada_en
    +marcas_incumplimiento
    +suspendido
    +version
    +agregar_bloque(id, ventana, ahora)
    +congelar_bloque(id, sesion_id, ahora)
    +bloquear_bloque(id, sesion_id, ahora)
    +liberar_bloque(id, sesion_id, ahora)
    +registrar_incumplimiento(motivo, ahora, politica)
  }
  class BloqueDeAgenda {
    <<Entity>>
    +bloque_id
    +ventana: VentanaHoraria
    +estado: EstadoBloque
    +sesion_id
  }
  class Sede {
    <<Entity de referencia>>
    +sede_id
    +cupo_maximo
    +radio_geocerca_m
  }

  class Dinero {
    <<Value Object>>
    +monto: Decimal
    +moneda = MXN
  }
  class VentanaHoraria {
    <<Value Object>>
    +inicio
    +fin
    +se_empalma()
    +contiene()
  }
  class DesgloseFinanciero {
    <<Value Object>>
    +bruto
    +comision
    +neto_tutor
    +calcular(bruto)$
  }
  class PorcentajeComision {
    <<Value Object>>
    +valor = 0.20
  }
  class EvidenciaAsistencia {
    <<Value Object>>
    +es_suficiente(modalidad) bool
  }
  class Calificacion {
    <<Value Object>>
    +puntos 1..5
  }

  class CalculadoraReembolso {
    <<Domain Service>>
    +calcular(monto, inicio, ahora)
  }
  class PoliticaCompensacion {
    <<Domain Service>>
    +calcular(monto)
  }
  class PoliticaSuspension {
    <<Domain Service>>
    +debe_suspender(marcas)
  }
  class Specification {
    <<Specification>>
    +es_satisfecha_por(c)
    +verificar(c)
    +and
    +or
    +not
  }
  class EventoDominio {
    <<Domain Event>>
    +nombre
    +agregado_id
    +ocurrido_en
    +datos
  }

  TransaccionSesion "1" *-- "0..1" Disputa
  TransaccionSesion "1" *-- "0..1" DesgloseFinanciero
  AgendaTutor "1" *-- "1..*" BloqueDeAgenda
  TransaccionSesion ..> AgendaTutor : tutor_id / bloque_id
  TransaccionSesion ..> Sede : sede_id (presencial)
  TransaccionSesion --> Dinero
  TransaccionSesion --> VentanaHoraria
  BloqueDeAgenda --> VentanaHoraria
  DesgloseFinanciero --> PorcentajeComision
  TransaccionSesion ..> CalculadoraReembolso
  TransaccionSesion ..> PoliticaCompensacion
  AgendaTutor ..> PoliticaSuspension
  TransaccionSesion ..> Specification : reserva_permitida / liberacion_permitida
  TransaccionSesion ..> EventoDominio : registra
  AgendaTutor ..> EventoDominio : registra
```

## Specifications implementadas (`src/domain/specifications.py`)

```text
reserva_permitida =  AnticipacionMinima(2 h)
                   AND PerfilVigente(7 días)
                   AND NOT TutorSuspendido
                   AND BloqueDisponible
                   AND (NOT EsPresencial OR CupoDisponible)

liberacion_permitida =  NOT DisputaAbierta
                      AND SesionCompletada
                      AND PagoConfirmado
                      AND RetencionCumplida(48 h)

paquete PIA:  PUEDE_PROCESARSE     = EstudianteActivo AND TieneLineas AND PagoAutorizado
              BENEFICIO_REFERENCIA = Preferente AND Total>=1500 AND NOT PromocionActiva
```

## Domain Events

`SesionReservada · PagoConfirmado · PagoRechazado · SesionConfirmada · CongelamientoExpirado · SesionCancelada ·
ReembolsoCalculado · SesionCompletada · SesionEnviadaARevision · NoShowRegistrado · DisputaAbierta · DisputaResuelta ·
FondosLiberados · SesionCalificada · HorarioCongelado · HorarioBloqueado · HorarioLiberado ·
MarcaIncumplimientoRegistrada · TutorSuspendido`
