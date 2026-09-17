/**
 * Servidor MCP (Model Context Protocol) sin estado, sobre HTTP.
 *
 * Es lo que permite que un agente use esto sin que nadie escriba código de
 * integración: se pega la URL /mcp en Claude, ChatGPT o el agente propio y
 * quedan disponibles las herramientas.
 *
 * Implementa JSON-RPC 2.0 directo, sin SDK, porque son cuatro métodos y así
 * el Worker no arrastra dependencias.
 */
import { consultarHorarios, consultarTarifa, resumenRegiones } from "./consultas";

const VERSION_PROTOCOLO = "2025-06-18";
const SERVIDOR = { name: "tarifas-gdmth", version: "1.0.0" };

const HERRAMIENTAS = [
  {
    name: "consultar_tarifa",
    title: "Consultar cargos de una tarifa de CFE",
    description:
      "Devuelve los cargos publicados por CFE para una tarifa, una ubicación y " +
      "un mes: cargo fijo ($/mes), energía en base, intermedia y punta ($/kWh), " +
      "y demanda por distribución y capacidad ($/kW). Se puede ubicar por " +
      "estado y municipio, o directamente por región tarifaria si ya se conoce.",
    inputSchema: {
      type: "object",
      properties: {
        estado: { type: "string", description: "Estado, p. ej. SONORA" },
        municipio: { type: "string", description: "Municipio, p. ej. NAVOJOA" },
        region: {
          type: "string",
          description: "Región tarifaria (NOROESTE, PENINSULAR, ...). Alternativa a estado/municipio.",
        },
        anio: { type: "integer", description: "Año, p. ej. 2026" },
        mes: { type: "integer", minimum: 1, maximum: 12, description: "Mes, 1 a 12" },
        tarifa: { type: "string", default: "GDMTH", description: "Clave de tarifa. Por omisión GDMTH." },
      },
      required: ["anio", "mes"],
    },
  },
  {
    name: "consultar_horarios",
    title: "Consultar periodos base, intermedia y punta",
    description:
      "Devuelve, para una región y una fecha, la temporada vigente (verano o " +
      "invierno), el tipo de día (hábil, sábado, domingo o festivo) y los " +
      "intervalos horarios de base, intermedia y punta. Si se pasa una hora, " +
      "indica además en qué periodo cae.",
    inputSchema: {
      type: "object",
      properties: {
        region: { type: "string", description: "Región tarifaria, p. ej. NOROESTE" },
        estado: { type: "string" },
        municipio: { type: "string" },
        fecha: { type: "string", description: "Fecha ISO, p. ej. 2026-08-15" },
        hora: { type: "string", description: "Hora opcional HH:MM, p. ej. 20:30" },
      },
      required: ["fecha"],
    },
  },
  {
    name: "listar_regiones",
    title: "Listar regiones y cobertura disponible",
    description:
      "Lista las regiones tarifarias conocidas, los estados con catálogo " +
      "cargado y los periodos disponibles por región.",
    inputSchema: { type: "object", properties: {} },
  },
];

function texto(obj: unknown) {
  return {
    content: [{ type: "text", text: JSON.stringify(obj, null, 2) }],
    structuredContent: obj as Record<string, unknown>,
    isError: false,
  };
}

function fallo(mensaje: string, extra?: unknown) {
  return {
    content: [{ type: "text", text: JSON.stringify({ error: mensaje, ...(extra as object) }, null, 2) }],
    isError: true,
  };
}

function llamar(nombre: string, args: Record<string, any>) {
  if (nombre === "consultar_tarifa") {
    const r = consultarTarifa(args);
    return "error" in r ? fallo(r.error as string, r) : texto(r);
  }
  if (nombre === "consultar_horarios") {
    const r = consultarHorarios(args);
    return "error" in r ? fallo(r.error as string, r) : texto(r);
  }
  if (nombre === "listar_regiones") return texto(resumenRegiones());
  return fallo(`herramienta desconocida: ${nombre}`);
}

function respuesta(id: unknown, resultado: unknown) {
  return { jsonrpc: "2.0", id, result: resultado };
}

function error(id: unknown, code: number, message: string) {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

function despachar(msg: any) {
  const { id, method, params } = msg ?? {};
  switch (method) {
    case "initialize":
      return respuesta(id, {
        protocolVersion: params?.protocolVersion ?? VERSION_PROTOCOLO,
        capabilities: { tools: { listChanged: false } },
        serverInfo: SERVIDOR,
        instructions:
          "Consulta cargos y horarios de las tarifas eléctricas que CFE publica " +
          "en México. No es un servicio oficial de CFE.",
      });
    case "ping":
      return respuesta(id, {});
    case "tools/list":
      return respuesta(id, { tools: HERRAMIENTAS });
    case "tools/call":
      return respuesta(id, llamar(params?.name, params?.arguments ?? {}));
    default:
      if (typeof method === "string" && method.startsWith("notifications/")) return null;
      return error(id, -32601, `método no soportado: ${method}`);
  }
}

export async function manejarMcp(req: Request, cors: Record<string, string>): Promise<Response> {
  if (req.method !== "POST") {
    return new Response(
      JSON.stringify({ error: "Este endpoint habla MCP por JSON-RPC sobre POST." }),
      { status: 405, headers: { "content-type": "application/json", ...cors } },
    );
  }
  let cuerpo: any;
  try {
    cuerpo = await req.json();
  } catch {
    return new Response(JSON.stringify(error(null, -32700, "JSON inválido")), {
      status: 400,
      headers: { "content-type": "application/json", ...cors },
    });
  }

  const lote = Array.isArray(cuerpo);
  const mensajes = lote ? cuerpo : [cuerpo];
  const salidas = mensajes.map(despachar).filter((r) => r !== null);

  if (salidas.length === 0) {
    // Solo notificaciones: el protocolo pide 202 sin cuerpo.
    return new Response(null, { status: 202, headers: cors });
  }
  return new Response(JSON.stringify(lote ? salidas : salidas[0]), {
    headers: { "content-type": "application/json", ...cors },
  });
}
