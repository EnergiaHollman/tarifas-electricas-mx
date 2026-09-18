/**
 * Prueba de extremo a extremo contra el servidor MCP REAL, ya desplegado en
 * Cloudflare — no contra una copia local empaquetada con esbuild como hacen
 * prueba_api.mjs y prueba_mcp.mjs.
 *
 * Corre la cadena completa por la que pasaría un agente de verdad:
 *
 *   initialize -> notifications/initialized -> tools/list -> tools/call
 *
 * incluida la resolución SONORA + NAVOJOA -> NOROESTE contra los datos que
 * hay hoy en el despliegue real, y compara los seis cargos de marzo de 2026
 * contra los valores que documenta el README (sin hardcodearlos aquí como
 * fuente de verdad: solo como referencia para detectar si el dato real
 * cambió o si algo se rompió).
 *
 *   MCP_URL=https://tarifas-electricas-mx.contacto-746.workers.dev/mcp \
 *     node pruebas/prueba_mcp_remoto.mjs
 *
 * Si no se da MCP_URL, usa el despliegue público del proyecto por omisión.
 * Necesita salida a Internet; si no la hay, lo dice y termina con código de
 * error distinto de una falla real, para no confundir "no hay red" con
 * "el servidor está mal".
 */
const URL_POR_OMISION = "https://tarifas-electricas-mx.contacto-746.workers.dev/mcp";
const MCP_URL = process.env.MCP_URL || URL_POR_OMISION;

let fallos = 0;
function check(nombre, obtenido, esperado) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado);
  console.log(`  ${ok ? "ok  " : "FALLA"} ${nombre}`);
  if (!ok) {
    console.log(`        esperado: ${JSON.stringify(esperado)}`);
    console.log(`        obtenido: ${JSON.stringify(obtenido)}`);
    fallos++;
  }
}

async function rpc(metodo, params, { id = 1 } = {}) {
  const cuerpo = id === undefined
    ? { jsonrpc: "2.0", method: metodo, params }
    : { jsonrpc: "2.0", id, method: metodo, params };
  const r = await fetch(MCP_URL, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json, text/event-stream" },
    body: JSON.stringify(cuerpo),
  });
  const texto = await r.text();
  return { status: r.status, cuerpo: texto ? JSON.parse(texto) : null };
}

console.log(`Probando el servidor MCP real en: ${MCP_URL}\n`);

// Verificación de red por adelantado: si esto falla, no tiene caso seguir
// interpretando lo demás como fallas del servidor.
let alcanzable = true;
try {
  const prueba = await fetch(MCP_URL, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 0, method: "ping" }),
  });
  if (!prueba.ok && prueba.status !== 400) alcanzable = false;
} catch {
  alcanzable = false;
}
if (!alcanzable) {
  console.log(`No se pudo alcanzar ${MCP_URL}.`);
  console.log("Esto no es una falla del servidor: puede ser que este entorno no tenga");
  console.log("salida a Internet, o que la URL no esté desplegada todavía. Corre este");
  console.log("archivo desde una máquina con acceso normal a la web para validar de verdad.");
  process.exit(2);
}

console.log("1. initialize");
let r = await rpc("initialize", {
  protocolVersion: "2025-06-18",
  capabilities: {},
  clientInfo: { name: "prueba-remota", version: "0.0" },
});
check("HTTP 200", r.status, 200);
check("jsonrpc 2.0", r.cuerpo?.jsonrpc, "2.0");
check("protocolVersion negociada", r.cuerpo?.result?.protocolVersion, "2025-06-18");
check("serverInfo.name", r.cuerpo?.result?.serverInfo?.name, "tarifas-electricas-mx");
check("declara capability tools", "tools" in (r.cuerpo?.result?.capabilities ?? {}), true);

console.log("\n2. notifications/initialized");
r = await rpc("notifications/initialized", undefined, { id: undefined });
check("202 Accepted", r.status, 202);

console.log("\n3. tools/list");
r = await rpc("tools/list", {});
check("HTTP 200", r.status, 200);
const nombres = (r.cuerpo?.result?.tools ?? []).map((t) => t.name);
check("las tres herramientas esperadas", nombres.sort(),
  ["consultar_horarios", "consultar_tarifa", "listar_regiones"].sort());

console.log("\n4. consultar_tarifa: SONORA + NAVOJOA -> NOROESTE, marzo 2026");
r = await rpc("tools/call", {
  name: "consultar_tarifa",
  arguments: { estado: "SONORA", municipio: "NAVOJOA", anio: 2026, mes: 3, tarifa: "GDMTH" },
});
check("HTTP 200", r.status, 200);
check("no marca isError", r.cuerpo?.result?.isError, false);
const sc = r.cuerpo?.result?.structuredContent ?? {};
check("resuelve la región sin que el agente la conozca de antemano", sc.region, "NOROESTE");
// Referencia documentada en el README para este periodo. Si el dato real
// cambió (por una recaptura o corrección de CFE), esta prueba lo hará
// evidente en vez de fallar en silencio.
check("cargos coinciden con la referencia del README", sc.cargos, {
  base: 0.9715, capacidad: 392.66, distribucion: 90.85,
  fijo: 197.77, intermedia: 1.5573, punta: 1.7262,
});

console.log("\n5. consultar_horarios");
r = await rpc("tools/call", {
  name: "consultar_horarios",
  arguments: { region: "NOROESTE", fecha: "2026-01-15", hora: "20:30" },
});
check("HTTP 200", r.status, 200);
check("no marca isError", r.cuerpo?.result?.isError, false);
check("resuelve un periodo horario", typeof r.cuerpo?.result?.structuredContent?.consulta?.periodo, "string");

console.log("\n6. listar_regiones");
r = await rpc("tools/call", { name: "listar_regiones", arguments: {} });
check("HTTP 200", r.status, 200);
check("devuelve regiones reales", Array.isArray(r.cuerpo?.result?.structuredContent?.regiones), true);
check("incluye NOROESTE", r.cuerpo?.result?.structuredContent?.regiones?.some((x) => x.region === "NOROESTE"), true);

console.log("\n7. Un error de protocolo también funciona en producción");
r = await rpc("tools/call", { name: "no_existe", arguments: {} });
check("herramienta inexistente -> error de protocolo -32602", r.cuerpo?.error?.code, -32602);

console.log();
if (fallos) {
  console.log(`${fallos} prueba(s) fallaron contra el servidor real.`);
  process.exit(1);
}
console.log("Todas las pruebas pasaron contra el servidor MCP real.");
