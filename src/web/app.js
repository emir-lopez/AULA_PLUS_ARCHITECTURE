// Interfaz de AulaPlus. Sin dependencias ni compilación: consume la API REST del mismo servidor.
// Las reglas de negocio viven en el dominio; aquí solo se decide qué formulario mostrar y cuándo.

const MIN = 60_000, HORA = 3_600_000;
const principal = document.querySelector("#contenido");
const dialogo = document.querySelector("#dialogo");

const estado = {
  params: null,
  desfase: 0,          // ms que la hora simulada va adelante (o atrás) de la real
  sesgo: 0,            // diferencia entre el reloj del servidor y el del navegador
  zona: "utc",
  dia: null,
  filtro: "Todas",
  estudiante: "E-001",
  rol: "cliente",      // "cliente" (estudiante) o "admin" (operación y soporte)
  tutores: [],
  sedes: [],
  sucio: false,
  turno: 0,
};

// ------------------------------------------------------------------ utilidades
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ahora = () => new Date(Date.now() + estado.sesgo + estado.desfase);
const zona = () => (estado.zona === "utc" ? "UTC" : undefined);
const fecha = (v) => (v instanceof Date ? v : new Date(v));

const formato = (opciones) => (v) => new Intl.DateTimeFormat("es-MX", { timeZone: zona(), ...opciones }).format(fecha(v));
const fFechaHora = formato({ weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fHora = formato({ hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fReloj = formato({ weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
const fDiaSemana = formato({ weekday: "short" });
const fDiaLargo = formato({ weekday: "long", day: "numeric", month: "long" });
const claveDia = (v) => new Intl.DateTimeFormat("en-CA", { timeZone: zona(), year: "numeric", month: "2-digit", day: "2-digit" }).format(fecha(v));
const numeroDia = (v) => new Intl.DateTimeFormat("es-MX", { timeZone: zona(), day: "numeric" }).format(fecha(v));
const pesos = (v) => new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" }).format(Number(v));

function duracion(ms) {
  const s = Math.round(Math.abs(ms) / 1000);
  const partes = [[Math.floor(s / 86400), "d"], [Math.floor(s / 3600) % 24, "h"], [Math.floor(s / 60) % 60, "min"], [s % 60, "s"]];
  const desde = partes.findIndex(([n]) => n > 0);
  if (desde === -1) return "0 s";
  return partes.slice(desde, desde + 2).filter(([n]) => n > 0).map(([n, u]) => `${n} ${u}`).join(" ");
}
const relativo = (v) => {
  const ms = fecha(v) - ahora();
  return ms >= 0 ? `en ${duracion(ms)}` : `hace ${duracion(ms)}`;
};
const cuenta = (v) => `<span data-hasta="${esc(fecha(v).toISOString())}">${relativo(v)}</span>`;

const NOMBRES = { EnRevision: "En revisión", NoShow: "No-show", EnLinea: "En línea", ReembolsoParcial: "Reembolso parcial" };
const nombre = (v) => NOMBRES[v] ?? v;
const insignia = (v) => `<span class="estado ${esc(v)}">${esc(nombre(v))}</span>`;

function leer(clave, respaldo) {
  try { return localStorage.getItem(`aulaplus.${clave}`) ?? respaldo; } catch { return respaldo; }
}
function guardar(clave, valor) {
  try { localStorage.setItem(`aulaplus.${clave}`, valor); } catch { /* sin almacenamiento: se usa el valor en memoria */ }
}

function avisar(texto) {
  const aviso = document.createElement("p");
  aviso.className = "aviso";
  aviso.textContent = texto;
  document.querySelector("#avisos").append(aviso);
  setTimeout(() => aviso.remove(), 5000);
}

// ------------------------------------------------------------------------ API
class ErrorApi extends Error {
  constructor(status, datos) {
    let codigo = `Error ${status}`, mensaje = "El servidor no pudo completar la operación.";
    if (datos?.codigo) {
      codigo = datos.codigo;
      mensaje = datos.mensaje && datos.mensaje !== datos.codigo ? datos.mensaje : "";
    } else if (Array.isArray(datos?.detail)) {
      codigo = "DatoInvalido";
      mensaje = datos.detail.map((d) => `${d.loc.slice(1).join(".")}: ${d.msg}`).join("; ");
    }
    super(mensaje);
    this.status = status;
    this.codigo = codigo;
  }
}

async function api(metodo, ruta, cuerpo) {
  const headers = {};
  if (cuerpo) headers["Content-Type"] = "application/json";
  if (estado.desfase) headers["X-Fecha-Simulada"] = ahora().toISOString();
  let respuesta;
  try {
    respuesta = await fetch(ruta, { method: metodo, headers, body: cuerpo ? JSON.stringify(cuerpo) : undefined });
  } catch {
    throw new ErrorApi(0, { codigo: "SinConexion", mensaje: "No hay conexión con el servidor. Revisa que la app esté en marcha." });
  }
  const datos = await respuesta.json().catch(() => null);
  if (!respuesta.ok) throw new ErrorApi(respuesta.status, datos);
  return datos;
}

// ---------------------------------------------------------------------- reloj
const reloj = {
  seccion: document.querySelector(".reloj"),
  hora: document.querySelector("#reloj-hora"),
  titulo: document.querySelector("#reloj-titulo"),
  real: document.querySelector("#reloj-real"),
  campo: document.querySelector("#reloj-fecha"),
};

const aCampoFecha = (d) => (estado.zona === "utc" ? d : new Date(d.getTime() - d.getTimezoneOffset() * MIN)).toISOString().slice(0, 16);
const deCampoFecha = (texto) => new Date(estado.zona === "utc" ? `${texto}:00Z` : texto);

function pintarReloj() {
  reloj.hora.textContent = `${fReloj(ahora())}${estado.zona === "utc" ? " UTC" : ""}`;
  for (const el of document.querySelectorAll("[data-hasta]")) el.textContent = relativo(el.dataset.hasta);
}

function fijarHora(momento) {
  const real = Date.now() + estado.sesgo;
  estado.desfase = momento ? fecha(momento).getTime() - real : 0;
  if (Math.abs(estado.desfase) < 1000) estado.desfase = 0;
  guardar("desfase", String(estado.desfase));
  const simulada = estado.desfase !== 0;
  reloj.seccion.classList.toggle("simulada", simulada);
  reloj.titulo.textContent = simulada ? "Hora simulada" : "Hora de la plataforma";
  reloj.real.hidden = !simulada;
  reloj.campo.value = aCampoFecha(ahora());
  pintarReloj();
}

// ---------------------------------------------------------------------- datos
async function cargarCatalogo() {
  [estado.tutores, estado.sedes] = await Promise.all([api("GET", "/tutores"), api("GET", "/sedes")]);
}
const esAdmin = () => estado.rol === "admin";

function pintarRol() {
  document.body.dataset.rol = estado.rol;
  document.querySelector("#marca-rol").textContent = esAdmin() ? "Administración" : "Estudiantes";
  for (const b of document.querySelectorAll("[data-rol]")) b.setAttribute("aria-pressed", String(b.dataset.rol === estado.rol));
  for (const el of document.querySelectorAll("[data-roles]")) el.hidden = !el.dataset.roles.split(" ").includes(estado.rol);
  document.querySelector('.menu a[data-vista="sesiones"]').textContent = esAdmin() ? "Sesiones" : "Mis sesiones";
  document.querySelector("#estudiante").value = estado.estudiante;
}

const tutor = (id) => estado.tutores.find((t) => t.tutor_id === id);
const nombreTutor = (id) => tutor(id)?.nombre ?? id;

async function siguienteSesionId() {
  const numeros = (await api("GET", "/sesiones")).map((s) => /^S-(\d+)$/.exec(s.sesion_id)?.[1]).filter(Boolean).map(Number);
  return `S-${String(Math.max(0, ...numeros) + 1).padStart(3, "0")}`;
}

// --------------------------------------------------------------------- vistas
const encabezado = (titulo, texto, extra = "") => `
  <div class="encabezado"><div><h1>${titulo}</h1>${texto ? `<p>${texto}</p>` : ""}</div>${extra}</div>`;
const vacio = (titulo, texto) => `<div class="vacio"><strong>${titulo}</strong>${texto}</div>`;

async function vistaAgenda() {
  await cargarCatalogo();
  const dias = [...new Set(estado.tutores.flatMap((t) => t.bloques.map((b) => claveDia(b.inicio))))].sort();
  if (!dias.length) {
    return encabezado("Agenda", "") + vacio("Todavía no hay horarios publicados",
      'Registra un tutor y publica sus horarios en <a href="#/catalogo">Tutores y sedes</a>.');
  }
  if (!dias.includes(estado.dia)) estado.dia = dias[0];
  const muestra = (dia) => estado.tutores.flatMap((t) => t.bloques).find((b) => claveDia(b.inicio) === dia).inicio;

  const tira = dias.map((d) => `
    <button type="button" class="dia" data-dia="${d}" aria-pressed="${d === estado.dia}">
      <span>${esc(fDiaSemana(muestra(d)))}</span><strong>${esc(numeroDia(muestra(d)))}</strong>
    </button>`).join("");

  const filas = estado.tutores.map((t) => {
    const bloques = t.bloques.filter((b) => claveDia(b.inicio) === estado.dia);
    const horarios = bloques.map((b) => {
      const rango = `${fHora(b.inicio)} a ${fHora(b.fin)}`;
      if (b.estado === "Disponible" && !t.suspendido && !esAdmin()) {
        return `<li><button type="button" class="horario" data-reservar="${esc(t.tutor_id)}|${esc(b.bloque_id)}">
          <strong>${rango}</strong><span>Disponible</span></button></li>`;
      }
      const etiqueta = { Disponible: t.suspendido ? "Tutor suspendido" : "Disponible", Congelado: "Apartado, falta el pago", Bloqueado: "Reservado" }[b.estado] ?? "No disponible";
      const contenido = `<strong>${rango}</strong><span>${etiqueta}</span>`;
      return b.sesion_id && esAdmin()
        ? `<li><a class="horario ${esc(b.estado)}" href="#/sesiones/${encodeURIComponent(b.sesion_id)}">${contenido}</a></li>`
        : `<li><span class="horario ${esc(b.estado)}">${contenido}</span></li>`;
    }).join("");
    return `
      <li class="tutor">
        <div class="tutor-datos">
          <h3>${esc(t.nombre)}</h3>
          <p>${pesos(t.tarifa_hora)} por hora${t.suspendido ? ` ${insignia("Suspendido")}` : ""}</p>
        </div>
        ${horarios ? `<ul class="horarios">${horarios}</ul>` : '<p class="suave">Sin horarios este día.</p>'}
      </li>`;
  }).join("");

  return encabezado(esAdmin() ? "Agenda" : "Reservar una tutoría", esAdmin()
    ? "Así ven los estudiantes la agenda. Las reservas se hacen desde la vista de cliente."
    : `Elige un horario disponible. La sesión debe empezar al menos ${estado.params.horas_anticipacion_minima} horas después de reservar.`) + `
    <div class="dias" role="group" aria-label="Día">${tira}</div>
    <h2 class="subtitulo">${esc(fDiaLargo(muestra(estado.dia)))}</h2>
    <ul class="tutores">${filas}</ul>`;
}

async function vistaSesiones() {
  const [todas] = await Promise.all([api("GET", "/sesiones"), cargarCatalogo()]);
  const sesiones = esAdmin() ? todas : todas.filter((s) => s.estudiante_id === estado.estudiante);
  const titulo = esAdmin() ? "Sesiones" : "Mis sesiones";
  const intro = esAdmin() ? "Todas las sesiones de la plataforma." : `Las sesiones del estudiante ${esc(estado.estudiante)}.`;
  if (!sesiones.length) {
    return encabezado(titulo, intro) + vacio("Aún no hay sesiones", esAdmin()
      ? "Aparecen aquí cuando un estudiante reserva."
      : 'Reserva la primera en <a href="#/agenda">Reservar</a>.');
  }
  const estados = ["Todas", ...new Set(sesiones.map((s) => s.estado))];
  if (!estados.includes(estado.filtro)) estado.filtro = "Todas";
  const visibles = sesiones.filter((s) => estado.filtro === "Todas" || s.estado === estado.filtro);
  const filtros = estados.map((e) => `
    <button type="button" class="filtro" data-filtro="${esc(e)}" aria-pressed="${e === estado.filtro}">${esc(nombre(e))}</button>`).join("");
  const filas = visibles.map((s) => `
    <tr>
      <td><a href="#/sesiones/${encodeURIComponent(s.sesion_id)}">${esc(s.sesion_id)}</a></td>
      <td>${esc(fFechaHora(s.inicio))}</td>
      <td>${esc(nombreTutor(s.tutor_id))}</td>
      ${esAdmin() ? `<td>${esc(s.estudiante_id)}</td>` : ""}
      <td>${esc(nombre(s.modalidad))}</td>
      <td class="num">${pesos(s.monto)}</td>
      <td>${insignia(s.estado)}</td>
    </tr>`).join("");
  return encabezado(titulo, intro) + `
    <div class="filtros" role="group" aria-label="Filtrar por estado">${filtros}</div>
    <div class="tabla-envoltura"><table>
      <thead><tr><th>Sesión</th><th>Inicio</th><th>Tutor</th>${esAdmin() ? "<th>Estudiante</th>" : ""}<th>Modalidad</th><th class="num">Monto</th><th>Estado</th></tr></thead>
      <tbody>${filas}</tbody>
    </table></div>`;
}

// Formularios de acción. `data-accion` elige el manejador de envío (ver ENVIOS).
const formulario = (accion, s, campos, boton, clase = "") => `
  <form data-accion="${accion}" data-sesion="${esc(s.sesion_id)}">
    ${campos ? `<div class="campos">${campos}</div>` : ""}
    <div class="acciones-form"><button class="boton ${clase}" type="submit">${boton}</button></div>
  </form>`;
const campo = (etiqueta, control, ayuda = "", clase = "") => `
  <div class="campo ${clase}">${etiqueta}${control}${ayuda ? `<p class="ayuda">${ayuda}</p>` : ""}</div>`;
const marca = (name, etiqueta, valor = "true", tipo = "checkbox", marcado = true) => `
  <label class="opcion"><input type="${tipo}" name="${name}" value="${esc(valor)}"${marcado ? " checked" : ""}> ${etiqueta}</label>`;
const quien = (s, leyenda, rol) => (rol === "cliente"
  ? `<input type="hidden" name="solicitante_id" value="${esc(s.estudiante_id)}">` : `
  <fieldset class="campo ancho"><legend>${leyenda}</legend><div class="opciones">
    ${marca("solicitante_id", `Estudiante (${esc(s.estudiante_id)})`, s.estudiante_id, "radio")}
    ${marca("solicitante_id", `Tutor (${esc(s.tutor_id)})`, s.tutor_id, "radio", false)}
  </div></fieldset>`);

function accionesDeSesion(s) {
  const p = estado.params, ya = ahora();
  const ini = fecha(s.inicio), fin = fecha(s.fin), congelado = fecha(s.congelado_hasta);
  const lista = [];
  const agregar = (rol, titulo, texto, form, disponible = true, saltar = null) => lista.push({ rol, titulo, texto, form, disponible, saltar });

  if (s.estado === "Reservada") {
    const vencido = ya > congelado;
    agregar("cliente", "Pagar la sesión", vencido
      ? "El apartado ya venció. Si se intenta pagar, la plataforma rechaza el cobro."
      : `El horario está apartado. El apartado vence ${cuenta(congelado)}.`,
    formulario("pago", s,
      campo('<label for="pago-monto">Monto cobrado</label>',
        `<input id="pago-monto" name="monto" type="text" inputmode="decimal" value="${esc(s.monto)}" required>`,
        `Debe ser exactamente ${pesos(s.monto)}.`) +
      campo('<label for="pago-resultado">Respuesta de la pasarela</label>',
        '<select id="pago-resultado" name="resultado"><option>Confirmado</option><option>Fallido</option></select>') +
      campo('<label for="pago-motivo">Motivo del rechazo</label>',
        '<input id="pago-motivo" name="motivo" type="text" maxlength="200">', "Solo si el pago falló.", "ancho"),
      "Pagar sesión"));
    agregar("admin", "Vencer el apartado", "Cancela la reserva sin pago y devuelve el horario a la agenda.",
      formulario("expirar", s, "", "Vencer apartado", "secundario"), vencido, new Date(congelado.getTime() + MIN));
  }

  if (s.estado === "Confirmada") {
    if (ya < ini) {
      const horas = (ini - ya) / HORA;
      const porcentaje = horas > 24 ? 100 : horas >= 6 ? 50 : 0;
      agregar("cliente", "Cancelar la sesión",
        `Faltan ${duracion(ini - ya)} para el inicio: el reembolso es del ${porcentaje} %, ${pesos(s.monto * porcentaje / 100)}.`,
        formulario("cancelar-estudiante", s, "", "Cancelar sesión", "peligro"));
      agregar("admin", "Cancelar a nombre del tutor",
        `El estudiante recupera el 100 %.${horas <= 24 ? " Como faltan 24 horas o menos, el tutor recibe una marca de incumplimiento." : ""}`,
        formulario("cancelar-tutor", s, "", "Cancelar sesión", "peligro"));
    }
    const enCurso = ya >= ini && ya < fin;
    if (ya < fin) {
      const restante = p.minutos_maximos_extension - s.minutos_extension;
      if (restante >= 15) {
        const tarifa = Number(tutor(s.tutor_id)?.tarifa_hora ?? 0);
        const opciones = [15, 30, 45, 60].filter((m) => m <= restante)
          .map((m) => `<option value="${m}">${m} minutos</option>`).join("");
        agregar("cliente", "Extender la sesión", `Se cobra dentro de la plataforma, en bloques de 15 minutos. Quedan ${restante} minutos disponibles.`,
          formulario("extension", s,
            campo('<label for="ext-minutos">Tiempo extra</label>', `<select id="ext-minutos" name="minutos" data-tarifa="${tarifa}">${opciones}</select>`) +
            campo('<label for="ext-monto">Monto cobrado</label>',
              `<input id="ext-monto" name="monto" type="text" inputmode="decimal" value="${(tarifa * 15 / 60).toFixed(2)}" required>`),
            "Extender sesión"), enCurso, ini);
      }
      if (s.modalidad === "EnLinea") {
        if (s.falla_conexion_desde) {
          agregar("admin", "Registrar la reconexión",
            `La conexión se cayó ${cuenta(s.falla_conexion_desde)}. Si la caída supera ${p.minutos_tolerancia_conexion} minutos, la sesión pasa a revisión de Soporte.`,
            formulario("reconexion", s, "", "Registrar reconexión"), enCurso, ini);
        } else {
          agregar("cliente", "Reportar una falla de conexión", "Avisa a Soporte que se cayó la conexión durante la sesión.",
            formulario("falla", s, quien(s, "", "cliente"), "Reportar falla", "secundario"), enCurso, ini);
          agregar("admin", "Reportar una falla de conexión", "A nombre de cualquiera de las dos partes, mientras la sesión está en curso.",
            formulario("falla", s, quien(s, "Quién reporta", "admin"), "Reportar falla", "secundario"), enCurso, ini);
        }
      }
    }
    const tolerancia = new Date(ini.getTime() + p.minutos_tolerancia_no_show * MIN);
    agregar("admin", "Registrar un no-show", "Si falta el tutor, el estudiante recupera el 100 % y el tutor recibe una marca.",
      formulario("no-show", s, `<fieldset class="campo ancho"><legend>Quién no se presentó</legend><div class="opciones">
        ${marca("parte_ausente", "Estudiante", "Estudiante", "radio")}${marca("parte_ausente", "Tutor", "Tutor", "radio", false)}
      </div></fieldset>`, "Registrar no-show", "peligro"), ya >= tolerancia, tolerancia);
    const asistencia = s.modalidad === "EnLinea"
      ? marca("conexion_tutor", "El tutor se conectó") + marca("conexion_estudiante", "El estudiante se conectó")
      : marca("checkin_dentro_de_geocerca", "Check-in dentro de la geocerca de la sede");
    agregar("admin", "Registrar la asistencia", "Con la evidencia completa la sesión queda completada y se calcula la comisión. Si falta algo, pasa a revisión de Soporte.",
      formulario("completar", s, `<fieldset class="campo ancho"><legend>Evidencia</legend><div class="opciones">
        ${asistencia}${marca("confirma_estudiante", "El estudiante confirma")}${marca("confirma_tutor", "El tutor confirma")}
      </div></fieldset>`, "Registrar asistencia"), ya >= fin, fin);
  }

  if (s.estado === "Completada") {
    const limite = new Date(fecha(s.completada_en).getTime() + p.horas_retencion * HORA);
    const disputaAbierta = s.disputa && !s.disputa.resuelta_en;
    if (s.estado_pago === "Confirmado" && !disputaAbierta) {
      agregar("admin", "Liberar el pago al tutor", `El pago se retiene ${p.horas_retencion} horas después de completar la sesión.`,
        formulario("liberacion", s, "", "Liberar pago"), ya >= limite, new Date(limite.getTime() + MIN));
      if (ya <= limite) {
        for (const rol of ["cliente", "admin"]) {
          agregar(rol, rol === "cliente" ? "Abrir una disputa" : "Abrir una disputa a nombre de una de las partes",
            `Detiene la liberación del pago al tutor hasta que Soporte resuelva. La ventana para disputar cierra ${cuenta(limite)}.`,
            formulario("disputa", s, quien(s, "Quién la abre", rol) +
              campo('<label for="disputa-motivo">Motivo</label>', '<textarea id="disputa-motivo" name="motivo" maxlength="500" required></textarea>', "", "ancho"),
            "Abrir disputa", "peligro"));
        }
      }
    }
    if (s.calificacion == null) {
      agregar("cliente", "Calificar la sesión", "", formulario("calificacion", s,
        `<fieldset class="campo ancho"><legend>Calificación del estudiante</legend><div class="opciones">
          ${[1, 2, 3, 4, 5].map((n) => marca("puntos", n, n, "radio", n === 5)).join("")}
        </div></fieldset>` +
        campo('<label for="cal-comentario">Comentario</label>', '<textarea id="cal-comentario" name="comentario" maxlength="500"></textarea>', "", "ancho"),
        "Guardar calificación", "secundario"));
    }
  }

  if (s.estado === "EnRevision") {
    const motivo = s.disputa && !s.disputa.resuelta_en
      ? `Disputa abierta por ${esc(s.disputa.abierta_por)}: "${esc(s.disputa.motivo)}". Soporte debe resolver ${cuenta(s.disputa.fecha_limite)}.`
      : `Motivo de la revisión: ${esc(nombre(s.motivo_revision))}.`;
    agregar("admin", "Resolver la revisión", `${motivo} A favor del tutor la sesión queda completada. A favor del estudiante se reembolsa el 100 %.`,
      formulario("resolucion", s, `<fieldset class="campo ancho"><legend>A favor de</legend><div class="opciones">
          ${marca("a_favor_de", "Tutor", "Tutor", "radio")}${marca("a_favor_de", "Estudiante", "Estudiante", "radio", false)}
        </div></fieldset>` +
        campo('<label for="res-texto">Resolución</label>', '<textarea id="res-texto" name="resolucion" maxlength="500" required></textarea>', "", "ancho"),
      "Guardar resolución"));
  }
  return lista;
}

function plazosDeSesion(s, eventos) {
  const p = estado.params, ya = ahora();
  const hitos = [];
  if (eventos[0]) hitos.push({ t: fecha(eventos[0].ocurrido_en), titulo: "Reserva" });
  hitos.push({ t: fecha(s.congelado_hasta), titulo: "Vence el apartado", margen: MIN, fijo: s.estado !== "Reservada" });
  hitos.push({ t: fecha(s.inicio), titulo: "Inicio" }, { t: fecha(s.fin), titulo: "Fin" });
  if (s.disputa) {
    hitos.push({ t: fecha(s.disputa.abierta_en), titulo: "Disputa abierta" });
    hitos.push({ t: fecha(s.disputa.fecha_limite), titulo: "Límite de mediación" });
  }
  if (s.liberado_en) {
    hitos.push({ t: fecha(s.liberado_en), titulo: "Pago liberado" });
  } else if (!["Cancelada", "NoShow"].includes(s.estado)) {
    const base = fecha(s.completada_en ?? s.fin);
    hitos.push({ t: new Date(base.getTime() + p.horas_retencion * HORA), margen: MIN,
      titulo: s.completada_en ? "Se puede liberar el pago" : "Liberación del pago, si no hay disputa" });
  }
  hitos.sort((a, b) => a.t - b.t);
  const posicion = hitos.findIndex((h) => h.t > ya);
  hitos.splice(posicion === -1 ? hitos.length : posicion, 0, { ahora: true });
  return `<ol class="plazos">${hitos.map((h) => (h.ahora
    ? `<li class="plazo ahora"><strong>Ahora</strong><span>${esc(fFechaHora(ya))}</span></li>`
    : `<li class="plazo ${h.t <= ya ? "pasado" : ""}"><strong>${h.titulo}</strong><span>${esc(fFechaHora(h.t))}</span>
        ${h.t > ya && !h.fijo && estado.params.permitir_fecha_simulada
    ? `<button type="button" class="boton secundario chico" data-ir="${new Date(h.t.getTime() + (h.margen ?? 0)).toISOString()}">Ir a este momento</button>` : ""}
      </li>`)).join("")}</ol>`;
}

async function vistaSesion(id) {
  let s, eventos;
  try {
    [s, eventos] = await Promise.all([
      api("GET", `/sesiones/${encodeURIComponent(id)}`), api("GET", `/sesiones/${encodeURIComponent(id)}/eventos`), cargarCatalogo()]);
  } catch (error) {
    if (error.status !== 404) throw error;
    return '<a class="regreso" href="#/sesiones">Todas las sesiones</a>' +
      vacio(`No existe la sesión ${esc(id)}`, "Revisa el identificador o vuelve a la lista.");
  }
  if (!esAdmin() && s.estudiante_id !== estado.estudiante) {
    return '<a class="regreso" href="#/sesiones">Mis sesiones</a>' + vacio(`La sesión ${esc(id)} es de otro estudiante`,
      `Estás viendo AulaPlus como ${esc(estado.estudiante)}. Cambia de estudiante o entra como administrador.`);
  }
  const sede = estado.sedes.find((x) => x.sede_id === s.sede_id);
  const acciones = accionesDeSesion(s);
  const mias = acciones.filter((a) => a.rol === estado.rol);
  const ahoraMismo = mias.filter((a) => a.disponible);
  const despues = mias.filter((a) => !a.disponible);
  const delOtro = [...new Set(acciones.filter((a) => a.rol !== estado.rol && a.disponible).map((a) => a.titulo.toLowerCase()))];
  const otroRol = !delOtro.length ? "" : `<p class="otro-rol">${esAdmin() ? "Desde la vista de cliente, el estudiante puede" : "El administrador puede"}:
    ${esc(delOtro.join(", "))}.</p>`;

  const filasCuenta = [
    ["Monto de la sesión", pesos(s.monto), "total"],
    s.minutos_extension ? ["Incluye extensión", `${s.minutos_extension} min`] : null,
    esAdmin() && s.comision != null ? ["Comisión de AulaPlus (20 %)", pesos(s.comision)] : null,
    esAdmin() && s.neto_tutor != null ? ["Neto para el tutor", pesos(s.neto_tutor)] : null,
    s.reembolso != null ? ["Reembolso al estudiante", pesos(s.reembolso)] : null,
    s.intentos_pago_fallidos ? ["Pagos rechazados", s.intentos_pago_fallidos] : null,
    s.calificacion != null ? ["Calificación", `${s.calificacion} de 5`] : null,
  ].filter(Boolean).map(([dt, dd, clase]) => `<div class="${clase ?? ""}"><dt>${dt}</dt><dd>${dd}</dd></div>`).join("");

  const listaEventos = eventos.map((e) => {
    const datos = Object.entries(e.datos ?? {}).map(([k, v]) => `${k}: ${v}`).join(", ");
    return `<li><strong>${esc(e.nombre)}</strong><p>${esc(fFechaHora(e.ocurrido_en))}${datos ? `. ${esc(datos)}` : ""}</p></li>`;
  }).join("");

  return `
    <a class="regreso" href="#/sesiones">${esAdmin() ? "Todas las sesiones" : "Mis sesiones"}</a>
    <div class="titulo-sesion"><h1>Sesión ${esc(s.sesion_id)}</h1>${insignia(s.estado)}</div>
    <dl class="ficha bloque">
      <div><dt>Tutor</dt><dd>${esc(nombreTutor(s.tutor_id))}</dd></div>
      <div><dt>Estudiante</dt><dd>${esc(s.estudiante_id)}</dd></div>
      <div><dt>Horario</dt><dd>${esc(fFechaHora(s.inicio))} a ${esc(fHora(s.fin))}</dd></div>
      <div><dt>Modalidad</dt><dd>${esc(nombre(s.modalidad))}${s.sede_id ? `, ${esc(sede?.nombre ?? s.sede_id)}` : ""}</dd></div>
      <div><dt>Pago</dt><dd>${insignia(s.estado_pago)}</dd></div>
    </dl>
    <section class="bloque panel" aria-labelledby="t-plazos">
      <h2 id="t-plazos">Plazos</h2>
      ${plazosDeSesion(s, eventos)}
    </section>
    <div class="bloque dos-columnas">
      <div>
        <section class="panel" aria-labelledby="t-acciones">
          <h2 id="t-acciones">${esAdmin() ? "Acciones del administrador" : "Qué puedes hacer ahora"}</h2>
          ${ahoraMismo.length ? ahoraMismo.map((a) => `
            <div class="accion"><h3>${a.titulo}</h3>${a.texto ? `<p>${a.texto}</p>` : ""}${a.form}</div>`).join("")
    : `<p class="suave">${despues.length ? "Nada por ahora. Las siguientes acciones se abren más adelante." : "No hay acciones pendientes de tu parte."}</p>`}
          ${otroRol}
        </section>
        ${despues.length ? `
        <section class="panel" aria-labelledby="t-despues">
          <h2 id="t-despues">Más adelante</h2>
          <ul class="despues">${despues.map((a) => `
            <li><div><h3>${a.titulo}</h3><p>Se abre ${cuenta(a.saltar)}.</p></div>
              ${estado.params.permitir_fecha_simulada ? `<button type="button" class="boton secundario chico" data-ir="${a.saltar.toISOString()}">Ir a ese momento</button>` : ""}
            </li>`).join("")}</ul>
        </section>` : ""}
      </div>
      <div>
        <section class="panel" aria-labelledby="t-cuenta">
          <h2 id="t-cuenta">Cuenta</h2>
          <dl class="cuenta">${filasCuenta}</dl>
        </section>
        ${esAdmin() ? `<section class="panel" aria-labelledby="t-eventos">
          <h2 id="t-eventos">Eventos de dominio</h2>
          <ul class="eventos">${listaEventos}</ul>
        </section>` : ""}
      </div>
    </div>`;
}

async function vistaSoporte() {
  const [disputas, pendientes] = await Promise.all([api("GET", "/soporte/disputas"), api("GET", "/liquidaciones/pendientes")]);
  const cola = disputas.length ? `<div class="tabla-envoltura"><table>
      <thead><tr><th>Sesión</th><th>Motivo</th><th>Abierta por</th><th>Límite para resolver</th><th></th></tr></thead>
      <tbody>${disputas.map((d) => `<tr>
        <td><a href="#/sesiones/${encodeURIComponent(d.sesion_id)}">${esc(d.sesion_id)}</a></td>
        <td>${esc(nombre(d.motivo))}</td>
        <td>${esc(d.abierta_por ?? "Sistema")}</td>
        <td>${d.fecha_limite ? `${esc(fFechaHora(d.fecha_limite))}, ${cuenta(d.fecha_limite)}` : "Sin límite"}</td>
        <td class="num"><a class="boton secundario chico" href="#/sesiones/${encodeURIComponent(d.sesion_id)}">Resolver</a></td>
      </tr>`).join("")}</tbody></table></div>`
    : vacio("No hay casos en revisión", "Aquí aparecen las disputas y las sesiones con evidencia incompleta.");
  const pagos = pendientes.length ? `<div class="tabla-envoltura"><table>
      <thead><tr><th>Sesión</th><th></th></tr></thead>
      <tbody>${pendientes.map((id) => `<tr>
        <td><a href="#/sesiones/${encodeURIComponent(id)}">${esc(id)}</a></td>
        <td class="num"><form data-accion="liberacion" data-sesion="${esc(id)}"><button class="boton chico" type="submit">Liberar pago</button></form></td>
      </tr>`).join("")}</tbody></table></div>`
    : vacio("No hay pagos listos para liberar", `Un pago se puede liberar ${estado.params.horas_retencion} horas después de completar la sesión, si no hay disputa abierta.`);
  return encabezado("Soporte", `Soporte tiene ${estado.params.horas_mediacion} horas para resolver cada disputa.`) + `
    <section class="bloque"><h2>Casos en revisión</h2>${cola}</section>
    <section class="bloque"><h2>Pagos listos para liberar</h2>${pagos}</section>`;
}

async function vistaIndicadores() {
  const k = await api("GET", "/indicadores");
  const porcentaje = (v) => (v == null ? "Sin datos" : `${(v * 100).toFixed(1)} %`);
  const estados = Object.entries(k.sesiones_por_estado);
  const total = estados.reduce((suma, [, n]) => suma + n, 0);
  return encabezado("Indicadores", "Los indicadores de la sección 9 del BRD, calculados sobre todas las sesiones.") + `
    <section class="bloque panel">
      <dl class="cifras">
        <div><dt>Sesiones completadas</dt><dd class="cifra">${porcentaje(k.tasa_completadas)}</dd><small>De las que ya cerraron</small></div>
        <div><dt>Ingreso por comisiones</dt><dd class="cifra">${pesos(k.ingreso_comisiones)}</dd><small>Solo pagos liberados</small></div>
        <div><dt>Total reembolsado</dt><dd class="cifra">${pesos(k.total_reembolsado)}</dd><small>${porcentaje(k.porcentaje_reembolsos)} de lo cobrado</small></div>
        <div><dt>Sesiones con disputa</dt><dd class="cifra">${k.sesiones_disputadas}</dd></div>
      </dl>
    </section>
    <section class="bloque"><h2>Sesiones por estado</h2>
      ${total ? `<div class="tabla-envoltura"><table>
        <thead><tr><th>Estado</th><th class="num">Sesiones</th><th class="num">Parte del total</th></tr></thead>
        <tbody>${estados.map(([e, n]) => `<tr><td>${insignia(e)}</td><td class="num">${n}</td><td class="num">${porcentaje(n / total)}</td></tr>`).join("")}</tbody>
      </table></div>` : vacio("Aún no hay sesiones", 'Reserva la primera desde la <a href="#/agenda">agenda</a>.')}
    </section>`;
}

async function vistaCatalogo() {
  await cargarCatalogo();
  const p = estado.params;
  const tutores = estado.tutores.length ? `<div class="tabla-envoltura"><table>
      <thead><tr><th>Clave</th><th>Nombre</th><th class="num">Tarifa por hora</th><th class="num">Marcas</th><th class="num">Horarios vigentes</th><th>Estado</th></tr></thead>
      <tbody>${estado.tutores.map((t) => `<tr>
        <td>${esc(t.tutor_id)}</td><td>${esc(t.nombre)}</td><td class="num">${pesos(t.tarifa_hora)}</td>
        <td class="num">${t.marcas_incumplimiento}</td><td class="num">${t.bloques.length}</td>
        <td>${insignia(t.suspendido ? "Suspendido" : "Disponible")}</td></tr>`).join("")}</tbody></table></div>`
    : vacio("No hay tutores registrados", "Registra el primero con el formulario de abajo.");
  const sedes = estado.sedes.length ? `<div class="tabla-envoltura"><table>
      <thead><tr><th>Clave</th><th>Nombre</th><th class="num">Cupo</th></tr></thead>
      <tbody>${estado.sedes.map((x) => `<tr><td>${esc(x.sede_id)}</td><td>${esc(x.nombre)}</td><td class="num">${x.cupo_maximo}</td></tr>`).join("")}</tbody>
    </table></div>` : vacio("No hay sedes registradas", "Las sesiones presenciales necesitan una sede.");
  const opcionesTutor = estado.tutores.map((t) => `<option value="${esc(t.tutor_id)}">${esc(t.nombre)}</option>`).join("");
  const manana = new Date(ahora().getTime() + 24 * HORA);
  manana.setUTCMinutes(0, 0, 0);

  return encabezado("Tutores y sedes", `Un tutor se suspende al acumular ${p.marcas_para_suspension} marcas de incumplimiento.
      Su perfil se oculta si pasa ${p.dias_vigencia_agenda} días sin actualizar la agenda.`) + `
    <section class="bloque"><h2>Tutores</h2>${tutores}</section>
    <section class="bloque dos-columnas">
      <form class="panel" data-accion="tutor">
        <h2>Registrar un tutor</h2>
        <div class="campos">
          ${campo('<label for="t-id">Clave</label>', '<input id="t-id" name="tutor_id" type="text" maxlength="40" required>', "Por ejemplo, T-004.")}
          ${campo('<label for="t-tarifa">Tarifa por hora</label>', '<input id="t-tarifa" name="tarifa_hora" type="text" inputmode="decimal" required>', "En pesos.")}
          ${campo('<label for="t-nombre">Nombre y materia</label>', '<input id="t-nombre" name="nombre" type="text" maxlength="120" required>', "", "ancho")}
        </div>
        <div class="acciones-form"><button class="boton" type="submit">Registrar tutor</button></div>
      </form>
      <form class="panel" data-accion="bloque">
        <h2>Publicar un horario</h2>
        ${estado.tutores.length ? `<div class="campos">
          ${campo('<label for="b-tutor">Tutor</label>', `<select id="b-tutor" name="tutor_id">${opcionesTutor}</select>`, "", "ancho")}
          ${campo('<label for="b-inicio">Inicio</label>', `<input id="b-inicio" name="inicio" type="datetime-local" value="${aCampoFecha(manana)}" required>`)}
          ${campo('<label for="b-fin">Fin</label>', `<input id="b-fin" name="fin" type="datetime-local" value="${aCampoFecha(new Date(manana.getTime() + HORA))}" required>`)}
        </div>
        <div class="acciones-form"><button class="boton" type="submit">Publicar horario</button></div>`
    : '<p class="suave">Primero registra un tutor.</p>'}
      </form>
    </section>
    <section class="bloque"><h2>Sedes</h2>${sedes}</section>
    <section class="bloque">
      <form class="panel" data-accion="sede" style="max-width: 640px">
        <h2>Registrar una sede</h2>
        <div class="campos">
          ${campo('<label for="s-id">Clave</label>', '<input id="s-id" name="sede_id" type="text" maxlength="40" required>')}
          ${campo('<label for="s-cupo">Cupo</label>', '<input id="s-cupo" name="cupo_maximo" type="number" min="1" required>', "Sesiones simultáneas.")}
          ${campo('<label for="s-nombre">Nombre</label>', '<input id="s-nombre" name="nombre" type="text" maxlength="120" required>', "", "ancho")}
        </div>
        <div class="acciones-form"><button class="boton" type="submit">Registrar sede</button></div>
      </form>
    </section>`;
}

// ------------------------------------------------------------------- reservar
async function abrirReserva(tutorId, bloqueId) {
  const t = tutor(tutorId), b = t?.bloques.find((x) => x.bloque_id === bloqueId);
  if (!b) return;
  const precio = Number(t.tarifa_hora) * (fecha(b.fin) - fecha(b.inicio)) / HORA;
  const id = await siguienteSesionId().catch(() => "");
  const sedes = estado.sedes.map((x) => `<option value="${esc(x.sede_id)}">${esc(x.nombre)} (cupo ${x.cupo_maximo})</option>`).join("");
  dialogo.innerHTML = `
    <form data-accion="reservar">
      <h2 id="dialogo-titulo">Reservar con ${esc(t.nombre)}</h2>
      <p class="resumen">${esc(fFechaHora(b.inicio))} a ${esc(fHora(b.fin))}. Cuesta ${pesos(precio)}.
        Reservas como ${esc(estado.estudiante)}.
        El horario queda apartado ${estado.params.minutos_congelamiento} minutos para que pagues.</p>
      <input type="hidden" name="estudiante_id" value="${esc(estado.estudiante)}"><input type="hidden" name="sesion_id" value="${esc(id)}">
      <input type="hidden" name="tutor_id" value="${esc(tutorId)}"><input type="hidden" name="bloque_id" value="${esc(bloqueId)}">
      <div class="campos">
        <fieldset class="campo ancho"><legend>Modalidad</legend><div class="opciones">
          ${marca("modalidad", "En línea", "EnLinea", "radio")}${marca("modalidad", "Presencial", "Presencial", "radio", false)}
        </div></fieldset>
        <div class="campo ancho" id="r-sede-campo" hidden>
          <label for="r-sede">Sede</label>
          ${sedes ? `<select id="r-sede" name="sede_id">${sedes}</select>` : '<p class="ayuda">No hay sedes registradas.</p>'}
        </div>
      </div>
      <div class="acciones-form">
        <button class="boton" type="submit">Reservar sesión</button>
        <button class="boton secundario" type="button" data-cerrar>No reservar</button>
      </div>
    </form>`;
  dialogo.showModal();
}

// --------------------------------------------------------------------- envíos
// Cada manejador recibe los campos del formulario y devuelve { aviso, ir? }.
const rutaSesion = (id, accion) => `/sesiones/${encodeURIComponent(id)}/${accion}`;
const ENVIOS = {
  async reservar(f) {
    const presencial = f.modalidad === "Presencial";
    await api("POST", "/sesiones", { sesion_id: f.sesion_id, estudiante_id: f.estudiante_id, tutor_id: f.tutor_id,
      bloque_id: f.bloque_id, modalidad: f.modalidad, sede_id: presencial ? f.sede_id ?? null : null });
    dialogo.close();
    return { aviso: `Sesión ${f.sesion_id} reservada`, ir: `#/sesiones/${encodeURIComponent(f.sesion_id)}` };
  },
  async pago(f, id) {
    await api("POST", rutaSesion(id, "pago"), { monto: f.monto, resultado: f.resultado, motivo: f.motivo || null });
    return { aviso: f.resultado === "Fallido" ? "Pago rechazado" : "Sesión pagada" };
  },
  async expirar(f, id) {
    const r = await api("POST", rutaSesion(id, "expirar"));
    return { aviso: r.expirada ? "Apartado vencido" : "El apartado todavía no vence" };
  },
  async "cancelar-estudiante"(f, id, s) {
    await api("POST", rutaSesion(id, "cancelacion-estudiante"), { solicitante_id: s.estudiante_id });
    return { aviso: "Sesión cancelada" };
  },
  async "cancelar-tutor"(f, id, s) {
    await api("POST", rutaSesion(id, "cancelacion-tutor"), { solicitante_id: s.tutor_id });
    return { aviso: "Sesión cancelada" };
  },
  async completar(f, id, s) {
    await api("POST", rutaSesion(id, "completar"), {
      conexion_tutor: f.conexion_tutor ? s.inicio : null, conexion_estudiante: f.conexion_estudiante ? s.inicio : null,
      checkin_dentro_de_geocerca: Boolean(f.checkin_dentro_de_geocerca),
      confirma_estudiante: Boolean(f.confirma_estudiante), confirma_tutor: Boolean(f.confirma_tutor) });
    return { aviso: "Asistencia registrada" };
  },
  async "no-show"(f, id) {
    await api("POST", rutaSesion(id, "no-show"), { parte_ausente: f.parte_ausente });
    return { aviso: "No-show registrado" };
  },
  async extension(f, id, s) {
    await api("POST", rutaSesion(id, "extension"), { estudiante_id: s.estudiante_id, minutos: Number(f.minutos), monto: f.monto });
    return { aviso: "Sesión extendida" };
  },
  async falla(f, id) {
    await api("POST", rutaSesion(id, "falla-conexion"), { solicitante_id: f.solicitante_id });
    return { aviso: "Falla reportada" };
  },
  async reconexion(f, id) {
    await api("POST", rutaSesion(id, "reconexion"));
    return { aviso: "Reconexión registrada" };
  },
  async calificacion(f, id, s) {
    await api("POST", rutaSesion(id, "calificacion"), { estudiante_id: s.estudiante_id, puntos: Number(f.puntos), comentario: f.comentario ?? "" });
    return { aviso: "Calificación guardada" };
  },
  async disputa(f, id) {
    await api("POST", rutaSesion(id, "disputa"), { solicitante_id: f.solicitante_id, motivo: f.motivo });
    return { aviso: "Disputa abierta" };
  },
  async resolucion(f, id) {
    await api("POST", rutaSesion(id, "resolucion"), { a_favor_de: f.a_favor_de, resolucion: f.resolucion });
    return { aviso: "Resolución guardada" };
  },
  async liberacion(f, id) {
    await api("POST", rutaSesion(id, "liberacion"));
    return { aviso: "Pago liberado" };
  },
  async tutor(f) {
    await api("POST", "/tutores", { tutor_id: f.tutor_id, nombre: f.nombre, tarifa_hora: f.tarifa_hora });
    return { aviso: "Tutor registrado" };
  },
  async bloque(f) {
    const inicio = deCampoFecha(f.inicio);
    const bloqueId = `B-${inicio.toISOString().slice(5, 16).replace(/[-:T]/g, "")}`;
    await api("POST", `/tutores/${encodeURIComponent(f.tutor_id)}/bloques`,
      { bloque_id: bloqueId, inicio: inicio.toISOString(), fin: deCampoFecha(f.fin).toISOString() });
    return { aviso: "Horario publicado" };
  },
  async sede(f) {
    await api("POST", "/sedes", { sede_id: f.sede_id, nombre: f.nombre, cupo_maximo: Number(f.cupo_maximo) });
    return { aviso: "Sede registrada" };
  },
};

function mostrarError(form, error) {
  let caja = form.querySelector(".error-form");
  if (!caja) {
    caja = document.createElement("p");
    caja.className = "error-form";
    caja.setAttribute("role", "alert");
    form.append(caja);
  }
  caja.innerHTML = `<code>${esc(error.codigo ?? "Error")}</code>${error.message ? `. ${esc(error.message)}` : ""}`;
}

document.addEventListener("submit", async (evento) => {
  const form = evento.target;
  if (form.id === "reloj-ir") {
    evento.preventDefault();
    fijarHora(deCampoFecha(reloj.campo.value));
    return pintar();
  }
  const manejador = ENVIOS[form.dataset.accion];
  if (!manejador) return;
  evento.preventDefault();
  const boton = form.querySelector('[type="submit"]');
  boton.disabled = true;
  try {
    const campos = Object.fromEntries(new FormData(form));
    const id = form.dataset.sesion;
    const sesion = id && manejador.length > 2 ? await api("GET", `/sesiones/${encodeURIComponent(id)}`) : null;
    const { aviso, ir } = await manejador(campos, id, sesion);
    avisar(aviso);
    estado.sucio = false;
    if (ir && location.hash !== ir) location.hash = ir; else await pintar();
  } catch (error) {
    if (!(error instanceof ErrorApi)) console.error(error);
    mostrarError(form, error);
    boton.disabled = false;
  }
});

document.addEventListener("click", (evento) => {
  const el = evento.target.closest("[data-rol], [data-salto], [data-ir], [data-dia], [data-filtro], [data-reservar], [data-cerrar], [data-reintentar], #reloj-real");
  if (!el) return;
  if (el.dataset.rol) {
    estado.rol = el.dataset.rol;
    guardar("rol", estado.rol);
    pintarRol();
    const inicio = esAdmin() ? "#/sesiones" : "#/agenda";
    if (location.hash !== inicio) { location.hash = inicio; return; }
  } else if (el.dataset.salto) fijarHora(new Date(ahora().getTime() + Number(el.dataset.salto)));
  else if (el.dataset.ir) fijarHora(el.dataset.ir);
  else if (el.id === "reloj-real") fijarHora(null);
  else if (el.dataset.dia) estado.dia = el.dataset.dia;
  else if (el.dataset.filtro) estado.filtro = el.dataset.filtro;
  else if (el.dataset.reservar) return void abrirReserva(...el.dataset.reservar.split("|"));
  else if ("cerrar" in el.dataset) return dialogo.close();
  estado.sucio = false;
  pintar();
});

document.addEventListener("change", (evento) => {
  const el = evento.target;
  if (el.id === "zona") {
    estado.zona = el.value;
    guardar("zona", el.value);
    reloj.campo.value = aCampoFecha(ahora());
    pintarReloj();
    return pintar();
  }
  if (el.id === "estudiante") {
    estado.estudiante = el.value.trim() || "E-001";
    guardar("estudiante", estado.estudiante);
    pintarRol();
    return pintar();
  }
  if (el.name === "minutos" && el.dataset.tarifa) {
    el.form.elements.monto.value = (Number(el.dataset.tarifa) * Number(el.value) / 60).toFixed(2);
  }
  if (el.name === "modalidad" && el.form.dataset.accion === "reservar") {
    el.form.querySelector("#r-sede-campo").hidden = el.value !== "Presencial";
  }
});
principal.addEventListener("input", () => { estado.sucio = true; });

// -------------------------------------------------------------------- arranque
const VISTAS = { agenda: vistaAgenda, sesiones: vistaSesiones, soporte: vistaSoporte, indicadores: vistaIndicadores, catalogo: vistaCatalogo };

async function pintar() {
  const turno = ++estado.turno;
  const [vista = "agenda", id] = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  const permitidas = esAdmin() ? Object.keys(VISTAS) : ["agenda", "sesiones"];
  const clave = permitidas.includes(vista) ? vista : esAdmin() ? "sesiones" : "agenda";
  for (const a of document.querySelectorAll(".menu a[data-vista]")) {
    if (a.dataset.vista === clave) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  let html;
  try {
    html = clave === "sesiones" && id ? await vistaSesion(id) : await VISTAS[clave]();
  } catch (error) {
    if (!(error instanceof ErrorApi)) console.error(error);
    html = vacio("No se pudo cargar esta sección",
      `${esc(error.message || error.codigo)} <button type="button" class="boton secundario chico" data-reintentar>Reintentar</button>`);
  }
  if (turno !== estado.turno) return;   // llegó una navegación más reciente
  principal.innerHTML = html;
  estado.sucio = false;
  document.title = `${principal.querySelector("h1")?.textContent ?? "AulaPlus"} | AulaPlus`;
}

async function iniciar() {
  estado.zona = leer("zona", "utc") === "local" ? "local" : "utc";
  estado.estudiante = leer("estudiante", "E-001");
  estado.rol = leer("rol", "cliente") === "admin" ? "admin" : "cliente";
  document.querySelector("#zona").value = estado.zona;
  pintarRol();
  try {
    estado.params = await api("GET", "/parametros");
    estado.sesgo = fecha(estado.params.ahora).getTime() - Date.now();
  } catch (error) {
    principal.innerHTML = vacio("No se pudo conectar con AulaPlus", `${esc(error.message)} Recarga la página cuando el servidor esté en marcha.`);
    return;
  }
  if (estado.params.permitir_fecha_simulada) {
    document.querySelector("#reloj-controles").hidden = false;
    const previo = Number(leer("desfase", "0")) || 0;
    fijarHora(previo ? new Date(Date.now() + estado.sesgo + previo) : null);
  } else {
    document.querySelector("#reloj-aviso").hidden = false;
    fijarHora(null);
  }
  setInterval(pintarReloj, 1000);
  setInterval(() => {
    const escribiendo = principal.contains(document.activeElement) && document.activeElement.matches("input, select, textarea");
    if (!dialogo.open && !estado.sucio && !escribiendo && !document.hidden) pintar();
  }, 20_000);
  window.addEventListener("hashchange", async () => {
    await pintar();
    window.scrollTo(0, 0);
    principal.focus({ preventScroll: true });
  });
  await pintar();
}

iniciar();
