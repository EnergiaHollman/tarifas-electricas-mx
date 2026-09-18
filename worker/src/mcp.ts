/**
 * Servidor MCP (Model Context Protocol) sin estado, sobre Streamable HTTP.
 *
 * Es lo que permite que un agente use esto sin que nadie escriba código de
 * integración: se pega la URL /mcp en Claude, ChatGPT o el agente propio y
 * quedan disponibles las herramientas.
 *
 * Implementa JSON-RPC 2.0 directo, sin el SDK oficial de MCP. Se evaluó
 * introducirlo y se descartó: el SDK está pensado para Node/Express o stdio,
 * y adaptar su transporte HTTP al runtime de Cloudflare Workers (fetch/
 * Request/Response, sin streams de Node) exige una capa de compatibilidad no
 * trivial, a cambio de un beneficio marginal frente a una implementación
 * manual de ~200 líneas que ya cubre el protocolo correctamente. Se prioriza
 * bajo mantenimiento y cero dependencias sobre "usar el SDK porque existe".
 *
 * Versión de protocolo: se declara y se negocia 2025-06-18 / 2025-11-25 (las
 * dos son, a efectos de transporte, la misma cosa; la diferencia entre ambas
 * es cosmética). Existe una revisión candidata 2026-07-28 que elimina el
 * handshake initialize y las sesiones por completo, pero al momento de
 * escribir esto sigue marcada como "release candidate" en la especificación
 * oficial (modelcontextprotocol.io la etiqueta "(latest)" sobre 2025-11-25,
 * no sobre 2026-07-28) y ningún cliente mayor (Claude, ChatGPT, MCP
 * Inspector) la habla todavía de forma consistente. Adoptarla ahora sería
 * apostar por un borrador; se documenta la decisión en vez de improvisarla.
 *
 * Sesiones: este servidor NUNCA emite Mcp-Session-Id. La especificación dice
 * que un servidor "MAY" asignar uno ("A server ... MAY assign a session ID");
 * no asignarlo es una opción explícitamente válida, no una carencia. Como
 * cada llamada a una herramienta es independiente y no hay estado que
 * correlacionar entre peticiones, no hay nada que una sesión resolviera aquí.
 *
 * Batching: eliminado de la especificación desde la revisión 2025-06-18
 * ("Remove support for JSON-RPC batching", PR #416). Un body que sea un
 * array ya no se acepta ni se intenta interpretar: se rechaza con un error
 * de protocolo, en vez de mantener una compatibilidad que el estándar
 * vigente retiró.
 */
import { consultarHorarios, consultarTarifa, resumenRegiones } from "./consultas";

// Versiones que este servidor entiende de verdad, de la más a la menos
// reciente. La primera es la que se ofrece cuando el cliente no pide, o pide,
// una versión que no reconocemos.
const VERSIONES_SOPORTADAS = ["2025-11-25", "2025-06-18"] as const;
const VERSION_POR_OMISION = VERSIONES_SOPORTADAS[0];

const SERVIDOR = { name: "tarifas-electricas-mx", version: "1.0.0" };

const HERRAMIENTAS = [
  {
    name: "consultar_tarifa",
    title: "Consultar cargos de una tarifa eléctrica de CFE",
    description:
      "Cargos de una tarifa eléctrica publicada por CFE (Comisión Federal de " +
      "Electricidad, México) para un mes concreto. Úsala cuando pregunten cuánto " +
      "cuesta la luz, el kWh, la demanda o el cargo fijo en algún lugar de México " +
      "en algún año y mes. Devuelve seis cargos: 'fijo' en $/mes; 'base', " +
      "'intermedia' y 'punta' -las tres franjas de energía- en $/kWh; y " +
      "'distribucion' y 'capacidad' -cargos por demanda- en $/kW. " +
      "Ubicación: pasa estado+municipio (la forma normal, p. ej. estado=SONORA, " +
      "municipio=NAVOJOA) y la herramienta resuelve sola a qué región tarifaria " +
      "pertenecen (SONORA+NAVOJOA -> NOROESTE); o pasa region directamente si ya " +
      "se conoce la región tarifaria (NOROESTE, PENINSULAR, BAJA CALIFORNIA, " +
      "...) y ahórrate estado/municipio. No mezcles las dos formas sin necesidad: " +
      "con region basta. Algunos municipios tienen más de una región tarifaria " +
      "válida; en ese caso la respuesta trae un resultado por cada una. " +
      "tarifa: la clave de la tarifa, en mayúsculas; si no se indica se asume " +
      "GDMTH (Gran Demanda en Media Tensión Horaria), que es la única con datos " +
      "capturados por ahora. mes va de 1 (enero) a 12 (diciembre), como entero, " +
      "no como nombre de mes.",
    inputSchema: {
      type: "object",
      properties: {
        estado: { type: "string", description: "Estado de México, p. ej. SONORA. Úsalo junto con municipio." },
        municipio: { type: "string", description: "Municipio, p. ej. NAVOJOA. Úsalo junto con estado." },
        region: {
          type: "string",
          description:
            "Región tarifaria ya conocida (NOROESTE, PENINSULAR, BAJA CALIFORNIA, ...). " +
            "Alternativa a estado+municipio: si la das, no hace falta dar estado ni municipio.",
        },
        anio: { type: "integer", description: "Año de cuatro dígitos, p. ej. 2026." },
        mes: {
          type: "integer",
          minimum: 1,
          maximum: 12,
          description: "Mes como número entero: 1 = enero ... 12 = diciembre.",
        },
        tarifa: {
          type: "string",
          default: "GDMTH",
          description: "Clave de la tarifa en mayúsculas. Por omisión GDMTH, la única con datos hoy.",
        },
      },
      required: ["anio", "mes"],
    },
  },
  {
    name: "consultar_horarios",
    title: "Consultar en qué periodo horario (base, intermedia o punta) cae una fecha y hora",
    description:
      "Para una región tarifaria y una fecha, calcula la temporada vigente " +
      "(verano o invierno, según las fechas que CFE publica para esa región), el " +
      "tipo de día (hábil, sábado, o domingo/festivo -incluye los días de " +
      "descanso obligatorio del artículo 74 de la LFT-) y las franjas horarias " +
      "de base, intermedia y punta de ese día. Si además se da una hora, indica " +
      "en qué periodo específico cae esa hora. Úsala cuando pregunten si tal " +
      "fecha u hora es horario punta, o cuáles son los horarios de una región. " +
      "Ubicación: region directamente, o estado+municipio para que se resuelva " +
      "sola (igual que en consultar_tarifa). fecha va en formato ISO AAAA-MM-DD " +
      "(p. ej. 2026-08-15). hora es opcional, formato HH:MM en 24 horas (p. ej. " +
      "20:30 para las 8:30 de la noche); si se omite, la respuesta trae las " +
      "franjas del día completo sin marcar ninguna hora en particular.",
    inputSchema: {
      type: "object",
      properties: {
        region: { type: "string", description: "Región tarifaria, p. ej. NOROESTE. Alternativa a estado+municipio." },
        estado: { type: "string", description: "Estado de México. Úsalo junto con municipio." },
        municipio: { type: "string", description: "Municipio. Úsalo junto con estado." },
        fecha: { type: "string", description: "Fecha en formato ISO AAAA-MM-DD, p. ej. 2026-08-15." },
        hora: { type: "string", description: "Hora opcional en formato 24h HH:MM, p. ej. 20:30." },
      },
      required: ["fecha"],
    },
  },
  {
    name: "listar_regiones",
    title: "Listar las regiones tarifarias y qué cobertura de datos hay",
    description:
      "Lista todas las regiones tarifarias que este servidor conoce, cuántos " +
      "periodos (mes-año) tiene capturados cada una, y qué estados están " +
      "cargados en el catálogo de municipios. Sin parámetros. Úsala para saber " +
      "qué regiones existen antes de llamar a consultar_tarifa por región, o " +
      "para diagnosticar por qué una consulta no encontró datos.",
    inputSchema: { type: "object", properties: {} },
  },
];

const NOMBRES_HERRAMIENTA = new Set(HERRAMIENTAS.map((h) => h.name));

// Todas de solo lectura sobre un JSON estático empaquetado en el propio
// Worker: no hay red, no hay CFE en vivo, no hay estado que mutar.
//   readOnlyHint    -> no modifican nada.
//   destructiveHint -> false (no aplicaría aunque readOnlyHint fuera false).
//   openWorldHint   -> false: el universo de respuestas posibles es el
//                      dataset ya capturado, cerrado y enumerable, no un
//                      sistema externo impredecible.
//   idempotentHint  -> deliberadamente OMITIDO. La propia especificación
//                      dice que solo es significativo para tools que NO son
//                      de solo lectura (readOnlyHint=false); declararlo aquí
//                      sería justo la anotación que no corresponde.
const ANOTACIONES_LECTURA = { readOnlyHint: true, destructiveHint: false, openWorldHint: false };
for (const h of HERRAMIENTAS) (h as any).annotations = ANOTACIONES_LECTURA;

function texto(obj: unknown) {
  return {
    content: [{ type: "text", text: JSON.stringify(obj, null, 2) }],
    structuredContent: obj as Record<string, unknown>,
    isError: false,
  };
}

/**
 * Error de EJECUCIÓN de una herramienta conocida: los argumentos tenían la
 * forma correcta pero el valor no aplica (mes 13, municipio inexistente,
 * región sin datos para ese mes...). Va en el resultado con isError:true,
 * como pide la especificación para "invalid input data" y "business logic
 * errors" — la llamada en sí fue válida, lo que falló es el dato.
 */
function fallo(mensaje: string, extra?: unknown) {
  return {
    content: [{ type: "text", text: JSON.stringify({ error: mensaje, ...(extra as object) }, null, 2) }],
    isError: true,
  };
}

function llamarHerramienta(nombre: unknown, args: unknown) {
  const a = (args && typeof args === "object" ? args : {}) as Record<string, any>;
  if (nombre === "consultar_tarifa") {
    const r = consultarTarifa(a);
    return "error" in r ? fallo(r.error as string, r) : texto(r);
  }
  if (nombre === "consultar_horarios") {
    const r = consultarHorarios(a);
    return "error" in r ? fallo(r.error as string, r) : texto(r);
  }
  if (nombre === "listar_regiones") return texto(resumenRegiones());
  return null; // nombre desconocido: lo resuelve el llamador como error de protocolo
}

function respuesta(id: unknown, resultado: unknown) {
  return { jsonrpc: "2.0", id, result: resultado };
}

/**
 * Error de PROTOCOLO: la petición en sí está mal formada (método que no
 * existe, herramienta que no existe, falta el nombre de la herramienta,
 * JSON roto). La especificación trae como ejemplo textual exactamente el
 * caso de una herramienta desconocida con código -32602, así que es el que
 * se sigue aquí.
 */
function error(id: unknown, code: number, message: string, data?: unknown) {
  return { jsonrpc: "2.0", id, error: { code, message, ...(data !== undefined ? { data } : {}) } };
}

function negociarVersion(pedida: unknown): string {
  if (typeof pedida === "string" && (VERSIONES_SOPORTADAS as readonly string[]).includes(pedida)) {
    return pedida;
  }
  return VERSION_POR_OMISION;
}

function despachar(msg: any) {
  const { id, method, params } = msg ?? {};

  if (typeof msg !== "object" || msg === null || Array.isArray(msg) || msg.jsonrpc !== "2.0") {
    return error(id ?? null, -32600, "Invalid Request: se esperaba un único objeto JSON-RPC 2.0.");
  }

  switch (method) {
    case "initialize":
      return respuesta(id, {
        protocolVersion: negociarVersion(params?.protocolVersion),
        capabilities: { tools: {} },
        serverInfo: SERVIDOR,
        instructions:
          "Consulta cargos y horarios de las tarifas eléctricas que CFE publica " +
          "en México. No es un servicio oficial de CFE ni está afiliado a ella. " +
          "Usa consultar_tarifa para cargos, consultar_horarios para saber si una " +
          "fecha/hora cae en periodo punta, y listar_regiones para ver la " +
          "cobertura disponible.",
      });

    case "ping":
      return respuesta(id, {});

    case "tools/list":
      return respuesta(id, { tools: HERRAMIENTAS });

    case "tools/call": {
      const nombre = params?.name;
      if (typeof nombre !== "string" || nombre.length === 0) {
        return error(id, -32602, "Invalid params: falta 'name' en tools/call.");
      }
      if (!NOMBRES_HERRAMIENTA.has(nombre)) {
        // Mismo código y misma redacción que usa el propio ejemplo de la
        // especificación para este caso exacto.
        return error(id, -32602, `Unknown tool: ${nombre}`);
      }
      return respuesta(id, llamarHerramienta(nombre, params?.arguments));
    }

    default:
      if (typeof method === "string" && method.startsWith("notifications/")) return null;
      return error(id, -32601, `Method not found: ${method}`);
  }
}

/** Encabezados comunes a toda respuesta JSON de este endpoint. */
function cabecerasJson(cors: Record<string, string>, version: string) {
  return { "content-type": "application/json", "mcp-protocol-version": version, ...cors };
}

export async function manejarMcp(req: Request, cors: Record<string, string>): Promise<Response> {
  // GET: la especificación permite abrir aquí un stream SSE para mensajes que
  // el servidor inicia por su cuenta. Este servidor no tiene nada que
  // empujar de forma proactiva -cada respuesta es la respuesta directa a una
  // llamada del cliente-, así que la propia especificación autoriza
  // responder 405 en vez de simular un stream vacío ("the server MUST either
  // return Content-Type: text/event-stream ... or else return HTTP 405").
  if (req.method === "GET") {
    return new Response(
      "Este servidor no ofrece un stream SSE por GET: cada respuesta llega " +
      "como respuesta directa de su propio POST.",
      { status: 405, headers: { "content-type": "text/plain; charset=utf-8", allow: "POST", ...cors } },
    );
  }

  // DELETE: solo tiene sentido para terminar una sesión, y este servidor
  // nunca emite Mcp-Session-Id (ver nota de cabecera del archivo). La
  // especificación autoriza explícitamente responder 405 en ese caso.
  if (req.method === "DELETE") {
    return new Response(
      "Este servidor no emite sesiones (Mcp-Session-Id), así que no hay nada que terminar.",
      { status: 405, headers: { "content-type": "text/plain; charset=utf-8", allow: "POST", ...cors } },
    );
  }

  if (req.method !== "POST") {
    return new Response("Este endpoint habla MCP por JSON-RPC 2.0 sobre POST.", {
      status: 405,
      headers: { "content-type": "text/plain; charset=utf-8", allow: "POST", ...cors },
    });
  }

  // La versión negociada en initialize decide qué se valida después; sin
  // ella, y sin el header presente, la especificación pide asumir 2025-03-26
  // por retrocompatibilidad. Aquí basta con no rechazar de más: solo se
  // devuelve 400 si el header SÍ viene y es un valor que no reconocemos en
  // absoluto (un valor vacío o ausente no cuenta como eso).
  const versionHeader = req.headers.get("mcp-protocol-version");
  if (versionHeader && !(VERSIONES_SOPORTADAS as readonly string[]).includes(versionHeader)) {
    return new Response(
      JSON.stringify(error(null, -32600, `Versión de protocolo no soportada: ${versionHeader}. ` +
        `Este servidor habla ${VERSIONES_SOPORTADAS.join(" o ")}.`)),
      { status: 400, headers: cabecerasJson(cors, VERSION_POR_OMISION) },
    );
  }
  const version = versionHeader ?? VERSION_POR_OMISION;

  let cuerpo: unknown;
  try {
    cuerpo = await req.json();
  } catch {
    return new Response(JSON.stringify(error(null, -32700, "Parse error: el cuerpo no es JSON válido.")), {
      status: 400,
      headers: cabecerasJson(cors, version),
    });
  }

  if (Array.isArray(cuerpo)) {
    // El batching se eliminó de la especificación en 2025-06-18. No se
    // interpreta el array; se rechaza tal cual, sin inventar soporte que el
    // estándar vigente ya no pide.
    return new Response(
      JSON.stringify(error(null, -32600,
        "Invalid Request: el batching JSON-RPC ya no forma parte de MCP (eliminado en 2025-06-18); " +
        "envía un único objeto por petición.")),
      { status: 400, headers: cabecerasJson(cors, version) },
    );
  }

  const salida = despachar(cuerpo);

  if (salida === null) {
    // Notificación o respuesta del cliente: 202 sin cuerpo, como pide el
    // protocolo cuando el servidor la acepta.
    return new Response(null, { status: 202, headers: { "mcp-protocol-version": version, ...cors } });
  }

  // En la propia llamada a "initialize" todavía no existe el header de
  // petición (el cliente aún no sabe qué versión usar); lo que decide la
  // versión ahí es el protocolVersion ya negociado dentro del resultado, no
  // el valor por omisión con el que se validó el header de entrada.
  const versionReal =
    (cuerpo as any)?.method === "initialize" && (salida as any)?.result?.protocolVersion
      ? (salida as any).result.protocolVersion
      : version;

  return new Response(JSON.stringify(salida), { headers: cabecerasJson(cors, versionReal) });
}
