/**
 * Pruebas del servidor MCP (Streamable HTTP sobre /mcp), sin desplegar nada.
 *
 *   cd worker && node pruebas/prueba_mcp.mjs
 *
 * Las pruebas de REST viven aparte, en prueba_api.mjs.
 */
import { BASE, crearVerificador, crearWorker } from "./_entorno.mjs";

const worker = await crearWorker();
const { check, contar } = crearVerificador();

/** POST JSON-RPC a /mcp con cabeceras razonables por omisión. */
async function rpc(metodo, params, { id = 1, version, sinContentType = false } = {}) {
  const headers = { accept: "application/json, text/event-stream" };
  if (!sinContentType) headers["content-type"] = "application/json";
  if (version) headers["mcp-protocol-version"] = version;
  const cuerpo = id === undefined
    ? { jsonrpc: "2.0", method: metodo, params }          // notificación: sin id
    : { jsonrpc: "2.0", id, method: metodo, params };
  const r = await worker.fetch(new Request(BASE + "/mcp", {
    method: "POST", headers, body: JSON.stringify(cuerpo),
  }));
  const texto = await r.text();
  return {
    status: r.status,
    version: r.headers.get("mcp-protocol-version"),
    cuerpo: texto ? JSON.parse(texto) : null,
  };
}

async function crudo(body, extraHeaders = {}) {
  const r = await worker.fetch(new Request(BASE + "/mcp", {
    method: "POST",
    headers: { "content-type": "application/json", ...extraHeaders },
    body,
  }));
  const texto = await r.text();
  return { status: r.status, cuerpo: texto ? JSON.parse(texto) : null };
}

// ---------------------------------------------------------------------
// 1. initialize
// ---------------------------------------------------------------------
console.log("1. initialize");
let r = await rpc("initialize", {
  protocolVersion: "2025-06-18",
  capabilities: {},
  clientInfo: { name: "prueba", version: "0.0" },
});
check("HTTP 200", r.status, 200);
check("jsonrpc 2.0", r.cuerpo.jsonrpc, "2.0");
check("eco del id", r.cuerpo.id, 1);
check("respeta la versión pedida por el cliente", r.cuerpo.result.protocolVersion, "2025-06-18");
check("serverInfo.name", r.cuerpo.result.serverInfo.name, "tarifas-electricas-mx");
check("trae serverInfo.version", typeof r.cuerpo.result.serverInfo.version, "string");
check("declara capability tools", "tools" in r.cuerpo.result.capabilities, true);
check("trae instructions", typeof r.cuerpo.result.instructions, "string");
check("header MCP-Protocol-Version en la respuesta", r.version, "2025-06-18");

r = await rpc("initialize", { protocolVersion: "2025-11-25" });
check("también acepta 2025-11-25", r.cuerpo.result.protocolVersion, "2025-11-25");

r = await rpc("initialize", { protocolVersion: "1999-01-01" });
check("versión desconocida: se ofrece la propia, no se inventa la pedida",
  r.cuerpo.result.protocolVersion, "2025-11-25");

r = await rpc("initialize", {});
check("sin protocolVersion: se ofrece la versión por omisión",
  r.cuerpo.result.protocolVersion, "2025-11-25");

// ---------------------------------------------------------------------
// 2. notifications/initialized
// ---------------------------------------------------------------------
console.log("\n2. notifications/initialized");
r = await rpc("notifications/initialized", undefined, { id: undefined });
check("202 Accepted", r.status, 202);
check("sin cuerpo", r.cuerpo, null);

// ---------------------------------------------------------------------
// 3. tools/list
// ---------------------------------------------------------------------
console.log("\n3. tools/list");
r = await rpc("tools/list", {});
check("HTTP 200", r.status, 200);
const nombres = r.cuerpo.result.tools.map((t) => t.name);
check("exactamente las tres herramientas esperadas", nombres,
  ["consultar_tarifa", "consultar_horarios", "listar_regiones"]);

const porNombre = Object.fromEntries(r.cuerpo.result.tools.map((t) => [t.name, t]));

check("consultar_tarifa: requiere anio y mes",
  porNombre.consultar_tarifa.inputSchema.required, ["anio", "mes"]);
check("consultar_tarifa: mes está acotado 1-12",
  [porNombre.consultar_tarifa.inputSchema.properties.mes.minimum,
   porNombre.consultar_tarifa.inputSchema.properties.mes.maximum], [1, 12]);
check("consultar_tarifa: tarifa por omisión GDMTH",
  porNombre.consultar_tarifa.inputSchema.properties.tarifa.default, "GDMTH");
check("consultar_horarios: requiere fecha",
  porNombre.consultar_horarios.inputSchema.required, ["fecha"]);
check("listar_regiones: sin parámetros requeridos",
  porNombre.listar_regiones.inputSchema.required ?? [], []);

for (const nombre of nombres) {
  const t = porNombre[nombre];
  check(`${nombre}: readOnlyHint`, t.annotations?.readOnlyHint, true);
  check(`${nombre}: destructiveHint`, t.annotations?.destructiveHint, false);
  check(`${nombre}: openWorldHint (dataset cerrado, sin red)`, t.annotations?.openWorldHint, false);
  check(`${nombre}: sin idempotentHint (solo aplica a tools de escritura)`,
    "idempotentHint" in (t.annotations ?? {}), false);
  check(`${nombre}: tiene descripción sustancial`, (t.description ?? "").length > 80, true);
}

// ---------------------------------------------------------------------
// 4. consultar_tarifa
// ---------------------------------------------------------------------
console.log("\n4. consultar_tarifa");
r = await rpc("tools/call", {
  name: "consultar_tarifa",
  arguments: { estado: "SONORA", municipio: "NAVOJOA", anio: 2026, mes: 3, tarifa: "GDMTH" },
});
check("HTTP 200", r.status, 200);
check("no marca isError", r.cuerpo.result.isError, false);
check("región resuelta: NOROESTE", r.cuerpo.result.structuredContent.region, "NOROESTE");
// Valores documentados en el README para Navojoa, Sonora, marzo de 2026.
// No se hardcodean en el Worker: esto solo confirma que la consulta llega al
// dato real ya capturado.
check("cargos exactos (referencia del README)", r.cuerpo.result.structuredContent.cargos, {
  base: 0.9715, capacidad: 392.66, distribucion: 90.85,
  fijo: 197.77, intermedia: 1.5573, punta: 1.7262,
});
check("content trae el mismo JSON en texto",
  JSON.parse(r.cuerpo.result.content[0].text).cargos.punta, 1.7262);

r = await rpc("tools/call", {
  name: "consultar_tarifa",
  arguments: { region: "NOROESTE", anio: 2026, mes: 3 },
});
check("también funciona dando la región directamente",
  r.cuerpo.result.structuredContent.cargos.punta, 1.7262);

// ---------------------------------------------------------------------
// 5. consultar_horarios
// ---------------------------------------------------------------------
console.log("\n5. consultar_horarios");
r = await rpc("tools/call", {
  name: "consultar_horarios",
  arguments: { region: "NOROESTE", fecha: "2026-01-15", hora: "20:30" },
});
check("HTTP 200", r.status, 200);
check("no marca isError", r.cuerpo.result.isError, false);
check("trae structuredContent", typeof r.cuerpo.result.structuredContent, "object");
check("temporada invierno", r.cuerpo.result.structuredContent.temporada, "invierno");
check("20:30 hábil de invierno es punta",
  r.cuerpo.result.structuredContent.consulta.periodo, "punta");

// ---------------------------------------------------------------------
// 6. listar_regiones
// ---------------------------------------------------------------------
console.log("\n6. listar_regiones");
r = await rpc("tools/call", { name: "listar_regiones", arguments: {} });
check("HTTP 200", r.status, 200);
check("devuelve regiones", Array.isArray(r.cuerpo.result.structuredContent.regiones), true);
check("incluye NOROESTE", r.cuerpo.result.structuredContent.regiones.some((x) => x.region === "NOROESTE"), true);

// ---------------------------------------------------------------------
// 7. Errores
// ---------------------------------------------------------------------
console.log("\n7. Errores");

// Mes inválido: la llamada es válida, el DATO no aplica -> isError, no error de protocolo.
r = await rpc("tools/call", { name: "consultar_tarifa", arguments: { region: "NOROESTE", anio: 2026, mes: 13 } });
check("mes inválido: HTTP 200 (no es un fallo de protocolo)", r.status, 200);
check("mes inválido: isError true", r.cuerpo.result.isError, true);
check("mes inválido: explica el problema",
  JSON.parse(r.cuerpo.result.content[0].text).error.includes("1 a 12"), true);

// Herramienta inexistente: la especificación lo trata como error de
// PROTOCOLO -32602, con el mismo texto que trae su propio ejemplo.
r = await rpc("tools/call", { name: "no_existe", arguments: {} });
check("herramienta inexistente: no es HTTP 200 con isError, es un error JSON-RPC",
  "error" in r.cuerpo, true);
check("herramienta inexistente: código -32602", r.cuerpo.error.code, -32602);
check("herramienta inexistente: mensaje", r.cuerpo.error.message, "Unknown tool: no_existe");

// tools/call sin 'name'.
r = await rpc("tools/call", { arguments: {} });
check("tools/call sin name: -32602", r.cuerpo.error.code, -32602);

// Método JSON-RPC inexistente.
r = await rpc("metodo/que/no/existe", {});
check("método inexistente: -32601", r.cuerpo.error.code, -32601);

// JSON inválido.
r = await crudo("{ esto no es json");
check("JSON inválido: HTTP 400", r.status, 400);
check("JSON inválido: -32700 Parse error", r.cuerpo.error.code, -32700);

// Argumentos inválidos dentro de una herramienta conocida (fecha con formato roto).
r = await rpc("tools/call", { name: "consultar_horarios", arguments: { region: "NOROESTE", fecha: "no-es-una-fecha" } });
check("fecha inválida: isError true", r.cuerpo.result.isError, true);

// Batch: eliminado de la especificación desde 2025-06-18; se rechaza, no se procesa.
r = await crudo(JSON.stringify([{ jsonrpc: "2.0", id: 1, method: "ping" }]));
check("batch (array): se rechaza, no se ejecuta en silencio", r.status, 400);
check("batch: error de protocolo", r.cuerpo.error.code, -32600);

// Header de versión explícitamente inválido.
r = await rpc("ping", {}, { version: "no-es-una-version" });
check("MCP-Protocol-Version desconocida en el header: HTTP 400", r.status, 400);

// GET y DELETE sobre /mcp: 405 según la especificación, con Allow: POST.
let resp = await worker.fetch(new Request(BASE + "/mcp", { method: "GET" }));
check("GET /mcp: 405 (sin sesiones ni stream que ofrecer)", resp.status, 405);
check("GET /mcp: Allow: POST", resp.headers.get("allow"), "POST");
resp = await worker.fetch(new Request(BASE + "/mcp", { method: "DELETE" }));
check("DELETE /mcp: 405 (no hay sesiones que terminar)", resp.status, 405);

// ---------------------------------------------------------------------
// 8. Regresión REST (recordatorio: la batería completa vive en prueba_api.mjs)
// ---------------------------------------------------------------------
console.log("\n8. REST no se rompió con los cambios de /mcp");
const getRest = async (ruta) => {
  const resp = await worker.fetch(new Request(BASE + ruta));
  return { status: resp.status, cuerpo: await resp.json() };
};
const restTarifa = await getRest("/v1/tarifa?estado=SONORA&municipio=NAVOJOA&anio=2026&mes=3");
check("REST /v1/tarifa sigue devolviendo los mismos cargos",
  restTarifa.cuerpo.cargos, { base: 0.9715, capacidad: 392.66, distribucion: 90.85,
                              fijo: 197.77, intermedia: 1.5573, punta: 1.7262 });
const restSalud = await getRest("/v1/salud");
check("REST /v1/salud sigue respondiendo", restSalud.cuerpo.ok, true);
console.log("  (batería completa de REST: node pruebas/prueba_api.mjs)");

console.log();
if (contar()) {
  console.log(`${contar()} prueba(s) fallaron.`);
  process.exit(1);
}
console.log("Todas las pruebas pasaron.");
