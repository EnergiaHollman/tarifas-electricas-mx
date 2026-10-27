/**
 * Pruebas de las tasas de referencia (Banxico -> D1 -> /v1/tasas-referencia y MCP), sin red ni deploy.
 *
 *   cd worker && node pruebas/prueba_tasas.mjs
 *
 * D1 se simula con node:sqlite y Banxico con un fetch falso.
 */
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { BASE, crearVerificador, crearWorker } from "./_entorno.mjs";

const worker = await crearWorker();
const { check, contar } = crearVerificador();

function d1() {
  const s = new DatabaseSync(":memory:");
  s.exec(readFileSync("migrations/0001_tipo_cambio.sql", "utf8"));
  s.exec(readFileSync("migrations/0002_tasas_referencia.sql", "utf8"));
  const prep = (sql) => {
    let p = [];
    const st = {
      bind(...v) { p = v; return st; },
      async first() { return s.prepare(sql).get(...p) ?? null; },
      async run() { s.prepare(sql).run(...p); return {}; },
    };
    return st;
  };
  return { DB: { prepare: prep, async batch(sts) { for (const x of sts) await x.run(); return []; } }, s };
}

/** Banxico falso: responde por serie pedida y registra las llamadas. */
function banxico(porSerie) {
  const llamadas = [];
  globalThis.fetch = async (url, init) => {
    llamadas.push({ url: String(url), token: new Headers(init?.headers).get("Bmx-Token") });
    // Como Banxico: solo devuelve las series que se pidieron en la URL.
    const pedidas = String(url).match(/\/series\/([^/]+)\/datos/)?.[1].split(",") ?? [];
    return Response.json({ bmx: { series: Object.entries(porSerie).filter(([id]) => pedidas.includes(id)).map(([idSerie, datos]) => ({ idSerie, datos })) } });
  };
  return llamadas;
}

const get = async (ruta, env) => {
  const r = await worker.fetch(new Request(BASE + ruta), env);
  return { status: r.status, cuerpo: await r.json() };
};

console.log("Tasas de referencia: cron");
const { DB, s } = d1();
// El cron consulta el tipo de cambio y las tasas; aquí el falso responde las tres series y cada módulo toma las suyas.
let llamadas = banxico({
  SF43718: [{ fecha: "07/10/2026", dato: "17.9780" }],
  SF60653: [{ fecha: "08/10/2026", dato: "17.9780" }],
  SF331451: [{ fecha: "06/10/2026", dato: "6.9400" }, { fecha: "07/10/2026", dato: "6.9500" }],
});
await worker.scheduled({}, { DB, BANXICO_TOKEN: "tok" });
check("pide SF331451 con el token", llamadas.some(l => l.url.includes("/series/SF331451/datos/2024-01-01/") && l.token === "tok"), true);
check("guarda las 2 filas de la tasa", s.prepare("SELECT count(*) AS n FROM tasa_referencia").get().n, 2);
check("el tipo de cambio sigue guardándose", s.prepare("SELECT count(*) AS n FROM tipo_cambio").get().n >= 1, true);
llamadas = banxico({ SF331451: [{ fecha: "07/10/2026", dato: "6.9500" }, { fecha: "08/10/2026", dato: "N/E" }, { fecha: "09/10/2026", dato: "" }] });
await worker.scheduled({}, { DB, BANXICO_TOKEN: "tok" });
check("con historial, solo pide los últimos días", llamadas.some(l => l.url.includes("SF331451") && l.url.includes("2024-01-01")), false);
check("no duplica ni guarda N/E ni vacíos", s.prepare("SELECT count(*) AS n FROM tasa_referencia").get().n, 2);
banxico({ SF331451: [{ fecha: "07/10/2026", dato: "7.0000" }] });
await worker.scheduled({}, { DB, BANXICO_TOKEN: "tok" });
check("corrige un valor que Banxico cambió", s.prepare("SELECT valor FROM tasa_referencia WHERE fecha = '2026-10-07'").get().valor, 7);

console.log("\nTasas de referencia: REST");
let r = await get("/v1/tasas-referencia?fecha=2026-10-06", { DB });
check("tasa del día", [r.status, r.cuerpo.serie, r.cuerpo.id_serie, r.cuerpo.valor, r.cuerpo.fecha], [200, "fondeo", "SF331451", 6.94, "2026-10-06"]);
r = await get("/v1/tasas-referencia?fecha=2026-10-11", { DB });
check("fin de semana: el último publicado antes", [r.cuerpo.fecha, r.cuerpo.valor], ["2026-10-07", 7]);
r = await get("/v1/tasas-referencia?fecha=2026-10-30", { DB });
check("aviso si el valor es viejo", typeof r.cuerpo.aviso_antiguedad, "string");
check("el aviso cita a Banxico, no a CFE", /Banco de México/.test(r.cuerpo.aviso) && !/CFE/.test(r.cuerpo.aviso), true);
r = await get("/v1/tasas-referencia?fecha=2020-01-01", { DB });
check("antes del historial da 404", r.status, 404);
r = await get("/v1/tasas-referencia?serie=tiie28", { DB });
check("serie inválida", r.cuerpo.error, "serie debe ser fondeo.");
r = await get("/v1/tasas-referencia?fecha=ayer", { DB });
check("fecha inválida", r.cuerpo.error, "fecha debe ir como AAAA-MM-DD.");
r = await get("/v1/tasas-referencia", {});
check("sin D1 configurada da error claro", r.status, 404);

console.log("\nTasas de referencia: MCP");
const mcp = await worker.fetch(new Request(BASE + "/mcp", {
  method: "POST",
  headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-protocol-version": "2025-06-18" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "consultar_tasa_referencia", arguments: { fecha: "2026-10-06" } } }),
}), { DB });
const m = await mcp.json();
check("consultar_tasa_referencia por MCP", m.result?.structuredContent?.valor, 6.94);

if (contar()) {
  console.log(`\n${contar()} prueba(s) fallaron.`);
  process.exit(1);
}
console.log("\nTodas las pruebas pasaron.");
