"""Aggregate TransaccionSesion: reserva, pago, ejecución, disputa y liquidación.

Orden en cada comando: (1) validar transición y reglas, (2) cambiar estado,
(3) registrar Domain Event. Si algo falla, el Aggregate no cambia.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from . import events as ev
from .events import EventoDominio
from .exceptions import DatoInvalido, ReglaDeNegocioViolada
from .policies import CalculadoraReembolso, ParametrosOperacion, PoliticaCompensacion
from .specifications import CandidatoLiberacion, SolicitudDeReserva, liberacion_permitida, reserva_permitida
from .state_machine import AccionSesion, EstadoPago, EstadoSesion, transicionar
from .value_objects import (
    Calificacion,
    DesgloseFinanciero,
    Dinero,
    EvidenciaAsistencia,
    Modalidad,
    ParteSesion,
    VentanaHoraria,
    exigir_zona_horaria,
)


@dataclass
class Disputa:
    motivo: str
    abierta_por: str
    abierta_en: datetime
    fecha_limite: datetime
    resolucion: str | None = None
    resuelta_en: datetime | None = None

    @property
    def abierta(self) -> bool:
        return self.resuelta_en is None


@dataclass
class TransaccionSesion:
    sesion_id: str
    estudiante_id: str
    tutor_id: str
    bloque_id: str
    ventana: VentanaHoraria
    modalidad: Modalidad
    monto: Dinero
    congelado_hasta: datetime
    sede_id: str | None = None
    estado: EstadoSesion = EstadoSesion.RESERVADA
    estado_pago: EstadoPago = EstadoPago.PENDIENTE
    intentos_pago_fallidos: int = 0
    desglose: DesgloseFinanciero | None = None
    completada_en: datetime | None = None
    monto_reembolso: Dinero | None = None
    motivo_revision: str | None = None
    parte_ausente: ParteSesion | None = None
    disputa: Disputa | None = None
    calificacion: Calificacion | None = None
    liberado_en: datetime | None = None
    minutos_extension: int = 0
    falla_conexion_desde: datetime | None = None
    version: int = 0
    eventos: list[EventoDominio] = field(default_factory=list)

    # ------------------------------------------------------------------ CU-01
    @classmethod
    def reservar(
        cls,
        *,
        sesion_id: str,
        estudiante_id: str,
        tutor_id: str,
        bloque_id: str,
        ventana: VentanaHoraria,
        modalidad: Modalidad,
        monto: Dinero,
        solicitud: SolicitudDeReserva,
        params: ParametrosOperacion,
        sede_id: str | None = None,
    ) -> TransaccionSesion:
        ahora = exigir_zona_horaria(solicitud.ahora)
        if modalidad == Modalidad.PRESENCIAL and not sede_id:
            raise DatoInvalido("SedeRequerida", "Una sesión presencial requiere sede")
        if monto.monto <= 0:
            raise DatoInvalido("MontoInvalido", "La tarifa de la sesión debe ser mayor a 0")
        reserva_permitida(params.horas_anticipacion_minima, params.dias_vigencia_agenda).verificar(solicitud)
        sesion = cls(
            sesion_id=sesion_id, estudiante_id=estudiante_id, tutor_id=tutor_id, bloque_id=bloque_id,
            ventana=ventana, modalidad=modalidad, monto=monto, sede_id=sede_id,
            congelado_hasta=ahora + timedelta(minutes=params.minutos_congelamiento),
        )
        sesion._registrar(ev.SESION_RESERVADA, ahora, monto=str(monto.monto),
                          congelado_hasta=sesion.congelado_hasta.isoformat())
        return sesion

    # ------------------------------------------------------------------ CU-02
    def confirmar_pago(self, monto_pagado: Dinero, ahora: datetime) -> None:
        """R-03/R-04: pago íntegro dentro de los 10 min de congelamiento (límite inclusivo, ADR-005)."""
        exigir_zona_horaria(ahora)
        siguiente = transicionar(self.estado, AccionSesion.CONFIRMAR_PAGO)
        if ahora > self.congelado_hasta:
            raise ReglaDeNegocioViolada("CongelamientoVencido", "El congelamiento de 10 minutos ya venció")
        if monto_pagado != self.monto:
            raise ReglaDeNegocioViolada(
                "MontoDePagoIncorrecto", f"Se esperaba {self.monto} y se recibió {monto_pagado}"
            )
        self.estado = siguiente
        self.estado_pago = EstadoPago.CONFIRMADO
        self._registrar(ev.PAGO_CONFIRMADO, ahora, monto=str(monto_pagado.monto))
        self._registrar(ev.SESION_CONFIRMADA, ahora)

    def registrar_pago_fallido(self, motivo: str, ahora: datetime) -> None:
        """H-13: el fallo se registra; la reserva sigue congelada para reintentar mientras no venza."""
        exigir_zona_horaria(ahora)
        transicionar(self.estado, AccionSesion.CONFIRMAR_PAGO)  # solo válido en Reservada
        if ahora > self.congelado_hasta:
            raise ReglaDeNegocioViolada("CongelamientoVencido", "El congelamiento ya venció")
        self.intentos_pago_fallidos += 1
        self._registrar(ev.PAGO_RECHAZADO, ahora, motivo=motivo or "sin motivo",
                        intento=self.intentos_pago_fallidos)

    def expirar_congelamiento(self, ahora: datetime) -> bool:
        exigir_zona_horaria(ahora)
        if self.estado != EstadoSesion.RESERVADA or ahora <= self.congelado_hasta:
            return False
        self.estado = transicionar(self.estado, AccionSesion.EXPIRAR)
        self._registrar(ev.CONGELAMIENTO_EXPIRADO, ahora)
        self._registrar(ev.SESION_CANCELADA, ahora, motivo="CongelamientoExpirado")
        return True

    # ------------------------------------------------------------------ CU-03
    def cancelar_por_estudiante(self, solicitante_id: str, ahora: datetime,
                                calculadora: CalculadoraReembolso) -> Dinero:
        exigir_zona_horaria(ahora)
        if solicitante_id != self.estudiante_id:
            raise ReglaDeNegocioViolada("SolicitanteNoEsElEstudiante")
        siguiente = transicionar(self.estado, AccionSesion.CANCELAR_POR_ESTUDIANTE)
        if ahora >= self.ventana.inicio:
            raise ReglaDeNegocioViolada("SesionYaInicio", "Solo se cancela antes del inicio")
        reembolso = calculadora.calcular(self.monto, self.ventana.inicio, ahora)
        self._aplicar_reembolso(reembolso)
        self.estado = siguiente
        self._registrar(ev.SESION_CANCELADA, ahora, motivo="CanceladaPorEstudiante")
        self._registrar(ev.REEMBOLSO_CALCULADO, ahora, monto=str(reembolso.monto))
        return reembolso

    def cancelar_por_tutor(self, solicitante_id: str, ahora: datetime,
                           compensacion: PoliticaCompensacion) -> tuple[Dinero, bool]:
        """US-08: el estudiante recibe el 100 %. Devuelve (reembolso, es_cancelacion_tardia)."""
        exigir_zona_horaria(ahora)
        if solicitante_id != self.tutor_id:
            raise ReglaDeNegocioViolada("SolicitanteNoEsElTutor")
        siguiente = transicionar(self.estado, AccionSesion.CANCELAR_POR_TUTOR)
        if ahora >= self.ventana.inicio:
            raise ReglaDeNegocioViolada("SesionYaInicio", "Después del inicio se registra un No-Show")
        reembolso = compensacion.calcular(self.monto)
        self._aplicar_reembolso(reembolso)
        self.estado = siguiente
        tardia = self.ventana.inicio - ahora <= timedelta(hours=24)
        self._registrar(ev.SESION_CANCELADA, ahora, motivo="CanceladaPorTutor", tardia=tardia)
        self._registrar(ev.REEMBOLSO_CALCULADO, ahora, monto=str(reembolso.monto))
        return reembolso, tardia

    # ------------------------------------------------------- ejecución (NB-01)
    def completar_con_evidencia(self, evidencia: EvidenciaAsistencia, ahora: datetime) -> EstadoSesion:
        """US-04/05/06/19: con evidencia suficiente -> Completada y desglose; si falta -> EnRevision."""
        exigir_zona_horaria(ahora)
        transicionar(self.estado, AccionSesion.COMPLETAR)
        if ahora < self.ventana.fin:
            raise ReglaDeNegocioViolada("SesionNoFinalizada", "La sesión aún no termina")
        if evidencia.es_suficiente(self.modalidad):
            self._marcar_completada(ahora)
        else:
            self.estado = transicionar(self.estado, AccionSesion.ENVIAR_A_REVISION)
            self.motivo_revision = "EvidenciaInsuficiente"
            self._registrar(ev.SESION_ENVIADA_A_REVISION, ahora, motivo=self.motivo_revision)
        return self.estado

    def registrar_no_show(self, parte_ausente: ParteSesion, ahora: datetime,
                          params: ParametrosOperacion, compensacion: PoliticaCompensacion) -> Dinero:
        """US-15: tras 10 min de tolerancia. Si falta el tutor, compensación total (US-08)."""
        exigir_zona_horaria(ahora)
        siguiente = transicionar(self.estado, AccionSesion.REGISTRAR_NO_SHOW)
        if ahora < self.ventana.inicio + timedelta(minutes=params.minutos_tolerancia_no_show):
            raise ReglaDeNegocioViolada("ToleranciaNoCumplida", "Aún no transcurren los 10 minutos")
        reembolso = Dinero.cero()
        if parte_ausente == ParteSesion.TUTOR:
            reembolso = compensacion.calcular(self.monto)
            self._aplicar_reembolso(reembolso)
        self.estado = siguiente
        self.parte_ausente = parte_ausente
        self._registrar(ev.NO_SHOW_REGISTRADO, ahora, parte_ausente=parte_ausente.value,
                        reembolso=str(reembolso.monto))
        return reembolso

    def _exigir_en_curso(self, ahora: datetime) -> None:
        if self.estado != EstadoSesion.CONFIRMADA:
            raise ReglaDeNegocioViolada("SesionNoEnCurso", f"La sesión está en estado {self.estado.value}")
        if not self.ventana.inicio <= ahora < self.ventana.fin:
            raise ReglaDeNegocioViolada("SesionNoEnCurso", "La operación solo aplica durante la sesión")

    def extender(self, estudiante_id: str, minutos: int, tarifa_hora: Dinero, monto_pagado: Dinero,
                 ahora: datetime, max_minutos: int = 60) -> Dinero:
        """US-12 / NB-08 / R-12: extensión pagada dentro de la plataforma, en bloques de 15 min."""
        exigir_zona_horaria(ahora)
        if estudiante_id != self.estudiante_id:
            raise ReglaDeNegocioViolada("SolicitanteNoEsElEstudiante")
        self._exigir_en_curso(ahora)
        if minutos <= 0 or minutos % 15 != 0:
            raise DatoInvalido("ExtensionInvalida", "La extensión se solicita en bloques de 15 minutos")
        if self.minutos_extension + minutos > max_minutos:
            raise ReglaDeNegocioViolada("ExtensionExcedeMaximo", f"Máximo {max_minutos} minutos de extensión")
        costo = tarifa_hora.por_porcentaje(Decimal(minutos) / Decimal(60))
        if monto_pagado != costo:
            raise ReglaDeNegocioViolada("MontoDeExtensionIncorrecto",
                                        f"La extensión cuesta {costo}; se recibió {monto_pagado}")
        self.ventana = VentanaHoraria(self.ventana.inicio, self.ventana.fin + timedelta(minutes=minutos))
        self.monto = self.monto.sumar(costo)
        self.minutos_extension += minutos
        self._registrar(ev.SESION_EXTENDIDA, ahora, minutos=minutos, costo=str(costo.monto),
                        nuevo_fin=self.ventana.fin.isoformat())
        return costo

    def reportar_falla_conexion(self, solicitante_id: str, ahora: datetime) -> None:
        """US-13 / NB-09: una parte reporta caída de conexión en sesión en línea; se notifica a Soporte."""
        exigir_zona_horaria(ahora)
        if solicitante_id not in (self.estudiante_id, self.tutor_id):
            raise ReglaDeNegocioViolada("SolicitanteNoEsParteDeLaSesion")
        if self.modalidad != Modalidad.EN_LINEA:
            raise ReglaDeNegocioViolada("SoloSesionesEnLinea", "La falla de conexión aplica a sesiones en línea")
        self._exigir_en_curso(ahora)
        if self.falla_conexion_desde is not None:
            raise ReglaDeNegocioViolada("FallaYaReportada")
        self.falla_conexion_desde = ahora
        self._registrar(ev.FALLA_CONEXION_REPORTADA, ahora, reportada_por=solicitante_id)

    def registrar_reconexion(self, ahora: datetime, params: ParametrosOperacion) -> EstadoSesion:
        """Dentro de la tolerancia (15 min) la sesión continúa; fuera de ella pasa a revisión de Soporte."""
        exigir_zona_horaria(ahora)
        if self.falla_conexion_desde is None:
            raise ReglaDeNegocioViolada("SinFallaReportada")
        transicionar(self.estado, AccionSesion.ENVIAR_A_REVISION)  # solo válido mientras está Confirmada
        caida = ahora - self.falla_conexion_desde
        self.falla_conexion_desde = None
        if caida <= timedelta(minutes=params.minutos_tolerancia_conexion):
            self._registrar(ev.CONEXION_RESTABLECIDA, ahora, minutos_caida=int(caida.total_seconds() // 60))
        else:
            self.estado = transicionar(self.estado, AccionSesion.ENVIAR_A_REVISION)
            self.motivo_revision = "FallaDeConexion"
            self._registrar(ev.SESION_ENVIADA_A_REVISION, ahora, motivo=self.motivo_revision)
        return self.estado

    def calificar(self, estudiante_id: str, calificacion: Calificacion, ahora: datetime) -> None:
        """US-18."""
        if estudiante_id != self.estudiante_id:
            raise ReglaDeNegocioViolada("SolicitanteNoEsElEstudiante")
        if self.estado != EstadoSesion.COMPLETADA:
            raise ReglaDeNegocioViolada("SesionNoCompletada", "Solo se califica una sesión Completada")
        if self.calificacion is not None:
            raise ReglaDeNegocioViolada("SesionYaCalificada")
        self.calificacion = calificacion
        self._registrar(ev.SESION_CALIFICADA, ahora, puntos=calificacion.puntos)

    # ------------------------------------------------------------------ CU-04
    def abrir_disputa(self, solicitante_id: str, motivo: str, ahora: datetime,
                      params: ParametrosOperacion) -> Disputa:
        exigir_zona_horaria(ahora)
        if solicitante_id not in (self.estudiante_id, self.tutor_id):
            raise ReglaDeNegocioViolada("SolicitanteNoEsParteDeLaSesion")
        if self.disputa is not None and self.disputa.abierta:
            raise ReglaDeNegocioViolada("DisputaYaAbierta")
        siguiente = transicionar(self.estado, AccionSesion.ABRIR_DISPUTA)
        if not motivo or not motivo.strip():
            raise DatoInvalido("MotivoRequerido", "La disputa requiere un motivo")
        if self.estado_pago != EstadoPago.CONFIRMADO or self.completada_en is None or (
            ahora > self.completada_en + timedelta(hours=params.horas_retencion)
        ):
            raise ReglaDeNegocioViolada("VentanaDeDisputaCerrada",
                                        "La ventana de disputas de 48 h ya concluyó")
        self.disputa = Disputa(motivo.strip(), solicitante_id, ahora,
                               ahora + timedelta(hours=params.horas_mediacion))
        self.estado = siguiente
        self._registrar(ev.DISPUTA_ABIERTA, ahora, fecha_limite=self.disputa.fecha_limite.isoformat())
        return self.disputa

    def resolver_revision(self, a_favor_de: ParteSesion, resolucion: str, ahora: datetime) -> None:
        """Soporte resuelve una disputa o una revisión por evidencia (US-06, R-08)."""
        exigir_zona_horaria(ahora)
        if not resolucion or not resolucion.strip():
            raise DatoInvalido("ResolucionRequerida", "Indique la resolución")
        if a_favor_de == ParteSesion.TUTOR:
            siguiente = transicionar(self.estado, AccionSesion.RESOLVER_A_FAVOR_TUTOR)
        else:
            siguiente = transicionar(self.estado, AccionSesion.RESOLVER_A_FAVOR_ESTUDIANTE)
        if self.disputa is not None and self.disputa.abierta:
            self.disputa.resolucion = resolucion.strip()
            self.disputa.resuelta_en = ahora
        if a_favor_de == ParteSesion.TUTOR:
            if self.completada_en is None:  # venía de revisión por evidencia
                self._marcar_completada(ahora, registrar_evento=True)
            self.estado = siguiente
        else:
            self._aplicar_reembolso(self.monto)
            self.estado = siguiente
        self.motivo_revision = None
        self._registrar(ev.DISPUTA_RESUELTA, ahora, a_favor_de=a_favor_de.value, resolucion=resolucion)

    # ------------------------------------------------------------------ CU-05
    def liberar_fondos(self, ahora: datetime, params: ParametrosOperacion) -> DesgloseFinanciero:
        exigir_zona_horaria(ahora)
        candidato = CandidatoLiberacion(
            sesion_completada=self.estado == EstadoSesion.COMPLETADA,
            pago_confirmado=self.estado_pago == EstadoPago.CONFIRMADO,
            disputa_abierta=self.disputa is not None and self.disputa.abierta,
            completada_en=self.completada_en,
            ahora=ahora,
        )
        liberacion_permitida(params.horas_retencion).verificar(candidato)
        assert self.desglose is not None  # se calcula siempre al completar
        self.estado_pago = EstadoPago.LIBERADO
        self.liberado_en = ahora
        self._registrar(ev.FONDOS_LIBERADOS, ahora, bruto=str(self.desglose.bruto.monto),
                        comision=str(self.desglose.comision.monto),
                        neto_tutor=str(self.desglose.neto_tutor.monto))
        return self.desglose

    # --------------------------------------------------------------- apoyo
    def _marcar_completada(self, ahora: datetime, registrar_evento: bool = True) -> None:
        self.desglose = DesgloseFinanciero.calcular(self.monto)
        self.completada_en = ahora
        if self.estado == EstadoSesion.CONFIRMADA:
            self.estado = transicionar(self.estado, AccionSesion.COMPLETAR)
        if registrar_evento:
            self._registrar(ev.SESION_COMPLETADA, ahora, comision=str(self.desglose.comision.monto),
                            neto_tutor=str(self.desglose.neto_tutor.monto))

    def _aplicar_reembolso(self, reembolso: Dinero) -> None:
        if reembolso.monto > self.monto.monto:  # INV-TS-10
            raise ReglaDeNegocioViolada("ReembolsoMayorAlPago")
        self.monto_reembolso = reembolso
        if self.estado_pago == EstadoPago.PENDIENTE:
            return
        if reembolso == self.monto:
            self.estado_pago = EstadoPago.REEMBOLSADO
        elif reembolso.monto > 0:
            self.estado_pago = EstadoPago.REEMBOLSO_PARCIAL

    def _registrar(self, nombre: str, ahora: datetime, **datos: object) -> None:
        self.eventos.append(EventoDominio(nombre, self.sesion_id, ahora, dict(datos)))

    def extraer_eventos(self) -> list[EventoDominio]:
        eventos, self.eventos = self.eventos, []
        return eventos
