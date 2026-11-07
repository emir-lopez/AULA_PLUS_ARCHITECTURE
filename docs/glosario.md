# Glosario de dominio (lenguaje ubicuo) — AulaPlus

Los términos se usan igual en el BRD, las historias, el BPMN, los diagramas y el código. La columna **Código** indica
la clase, valor o evento que lo implementa.

| # | Término | Definición | Código |
|---|---|---|---|
| 1 | Sesión | Tutoría programada entre un estudiante y un tutor, presencial o en línea. | `TransaccionSesion` |
| 2 | Transacción de sesión | Ciclo completo de una sesión: reserva, pago, ejecución, disputa y liquidación. Raíz de agregado. | `TransaccionSesion` |
| 3 | Reserva (proceso) | Acción por la que el estudiante agenda una sesión; incluye el pago. | `ServicioReservaSesion.reservar_sesion` |
| 4 | Reservada (estado) | Sesión con horario congelado y pago pendiente. | `EstadoSesion.RESERVADA` |
| 5 | Confirmada | Sesión con pago confirmado y horario bloqueado. | `EstadoSesion.CONFIRMADA` |
| 6 | Completada | Sesión realizada con evidencia suficiente o validada por Soporte; genera comisión. | `EstadoSesion.COMPLETADA` |
| 7 | En revisión | Sesión con evidencia insuficiente o con disputa abierta; la atiende Soporte. | `EstadoSesion.EN_REVISION` |
| 8 | Cancelada | Sesión terminada sin realizarse (vencimiento, cancelación o resolución a favor del estudiante). | `EstadoSesion.CANCELADA` |
| 9 | No-Show | Una de las partes no se presentó tras la tolerancia de 10 minutos. | `EstadoSesion.NO_SHOW` |
| 10 | Agenda del tutor | Conjunto de bloques de disponibilidad de un tutor. Raíz de agregado. | `AgendaTutor` |
| 11 | Bloque de agenda | Intervalo de tiempo con identidad y estado de disponibilidad. | `BloqueDeAgenda` |
| 12 | Disponible / Congelado / Bloqueado | Estados del bloque: libre; retenido 10 min durante el pago; ocupado por una sesión pagada. | `EstadoBloque` |
| 13 | Congelamiento | Retención temporal (10 min) del horario mientras se procesa el pago. | `congelado_hasta` |
| 14 | Modalidad | Forma de la tutoría: presencial o en línea. | `Modalidad` |
| 15 | Sede | Espacio físico para sesiones presenciales con cupo máximo y geocerca. | `Sede` |
| 16 | Sobrecupo | Situación en que una sede tendría más sesiones simultáneas que su cupo; está prohibida. | `CupoDisponibleSpec` |
| 17 | Dinero | Monto en MXN con dos decimales, nunca negativo, calculado con `Decimal`. | `Dinero` |
| 18 | Comisión | Porcentaje (20 %) que AulaPlus retiene de cada sesión completada. | `PorcentajeComision` |
| 19 | Desglose financiero | Bruto, comisión y neto del tutor de una sesión; comisión + neto = bruto. | `DesgloseFinanciero` |
| 20 | Pago | Cobro de la sesión dentro de la plataforma; estados Pendiente, Confirmado, Liberado, Reembolsado, ReembolsoParcial. | `EstadoPago` |
| 21 | Pago fallido | Rechazo de la pasarela; la reserva sigue congelada para reintentar. | `PagoRechazado` |
| 22 | Reembolso | Dinero devuelto al estudiante según anticipación (100/50/0 %) o responsabilidad del tutor (100 %). | `CalculadoraReembolso`, `PoliticaCompensacion` |
| 23 | Ventana de disputas / retención | 48 h posteriores a Completada en las que el pago queda retenido y se puede abrir disputa. | `RetencionCumplidaSpec` |
| 24 | Disputa | Reclamo de una parte sobre una sesión completada; se media en máximo 72 h. | `Disputa` |
| 25 | Mediación | Resolución de Soporte a favor del tutor (Completada) o del estudiante (Cancelada con reembolso). | `resolver_revision` |
| 26 | Liberación / dispersión | Entrega del neto al tutor tras la retención y sin disputa abierta. | `liberar_fondos`, `FondosLiberados` |
| 27 | Evidencia de asistencia | Datos objetivos de que la sesión ocurrió: conexión, geocerca y confirmación mutua. | `EvidenciaAsistencia` |
| 28 | Marca de incumplimiento | Registro contra el tutor por No-Show o cancelación tardía (≤24 h). | `registrar_incumplimiento` |
| 29 | Suspensión | Estado del tutor al acumular 3 marcas; no aparece en búsquedas ni recibe reservas. | `TutorSuspendidoSpec` |
| 30 | Perfil vigente | Tutor que actualizó su agenda en los últimos 7 días. | `PerfilVigenteSpec` |
| 31 | Domain Event | Hecho ya ocurrido, nombrado en pasado, guardado en el outbox junto con el cambio. | `EventoDominio` |
| 32 | Demanda | Cantidad de estudiantes interesados en reservar con un tutor (corrige la definición duplicada de U2). | KPI (futuro) |
| 33 | Marketplace | Modelo de negocio en que AulaPlus conecta oferta (tutores) y demanda (estudiantes) sin impartir la tutoría. | — |
