/**
 * Pruebas del tipo de cambio (Banxico -> D1 -> /v1/tipo-cambio y MCP), sin red ni deploy.
 *
 *   cd worker && node pruebas/prueba_tipo_cambio.mjs
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

/** Banxico falso: responde las dos series en el rango pedido y registra las llamadas. */
function banxico(datos) {
  const llamadas = [];
  globalThis.fetch = async (url, init) => {
    llamadas.push({ url: String(url), token: new Headers(init?.headers).get("Bmx-Token") });
    return Response.json({ bmx: { series: [
      { idSerie: "SF43718", datos: datos.fix },
      { idSerie: "SF60653", datos: datos.dof },
    ] } });
  };
  return llamadas;
}

const get = async (ruta, env) => {
  const r = await worker.fetch(new Request(BASE + ruta), env);
  return { status: r.status, cuerpo: await r.json() };
};

console.log("Tipo de cambio: cron");
const { DB, s } = d1();
let llamadas = banxico({
  fix: [{ fecha: "06/10/2026", dato: "18.0123" }, { fecha: "07/10/2026", dato: "17.9780" }],
  dof: [{ fecha: "07/10/2026", dato: "18.0123" }, { fecha: "08/10/2026", dato: "17.9780" }],
});
await worker.scheduled({}, { DB, BANXICO_TOKEN: "tok" });
check("pide las dos series con el token", llamadas[0].url.includes("/series/SF43718,SF60653/datos/2024-01-01/"), true);
check("token en el header", llamadas[0].token, "tok");
check("guarda las 4 filas", s.prepare("SELECT count(*) AS n FROM tipo_cambio").get().n, 4);
llamadas = banxico({ fix: [{ fecha: "07/10/2026", dato: "17.9780" }, { fecha: "08/10/2026", dato: "N/E" }], dof: [] });
await worker.scheduled({}, { DB, BANXICO_TOKEN: "tok" });
check("con historial, solo pide los últimos días", llamadas[0].url.includes("2024-01-01"), false);
check("no duplica ni guarda N/E", s.prepare("SELECT count(*) AS n FROM tipo_cambio").get().n, 4);
const sinToken = await worker.scheduled({}, { DB }).then(() => "sin error");
llamadas = banxico({ fix: [], dof: [] });
await worker.scheduled({ cron: "* * * * *" }, { DB, BANXICO_TOKEN: "tok" });
check("ignora un cron que no está en la configuración", llamadas.length, 0);
await worker.scheduled({ cron: "30 18 * * *" }, { DB, BANXICO_TOKEN: "tok" });
check("corre con un cron de la configuración", llamadas.length, 1);
check("sin token no truena el cron", sinToken, "sin error");

console.log("\nTipo de cambio: REST");
let r = await get("/v1/tipo-cambio?fecha=2026-10-07", { DB });
check("FIX del día", [r.status, r.cuerpo.serie, r.cuerpo.id_serie, r.cuerpo.valor, r.cuerpo.fecha], [200, "fix", "SF43718", 17.978, "2026-10-07"]);
r = await get("/v1/tipo-cambio?fecha=2026-10-11", { DB });
check("fin de semana: el último publicado antes", [r.cuerpo.fecha, r.cuerpo.valor], ["2026-10-07", 17.978]);
r = await get("/v1/tipo-cambio?fecha=2026-10-07&serie=dof", { DB });
check("DOF: serie por fecha de liquidación", [r.cuerpo.id_serie, r.cuerpo.valor], ["SF60653", 18.0123]);
r = await get("/v1/tipo-cambio?fecha=2026-10-30", { DB });
check("aviso si el valor es viejo", typeof r.cuerpo.aviso_antiguedad, "string");
check("el aviso cita a Banxico, no a CFE", /Banco de México/.test(r.cuerpo.aviso) && !/CFE/.test(r.cuerpo.aviso), true);
r = await get("/v1/tipo-cambio?fecha=2020-01-01", { DB });
check("antes del historial da 404", r.status, 404);
r = await get("/v1/tipo-cambio?serie=euro", { DB });
check("serie inválida", r.cuerpo.error, "serie debe ser fix o dof.");
r = await get("/v1/tipo-cambio", {});
check("sin D1 configurada da error claro", r.status, 404);

console.log("\nTipo de cambio: MCP");
const mcp = await worker.fetch(new Request(BASE + "/mcp", {
  method: "POST",
  headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-protocol-version": "2025-06-18" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "consultar_tipo_cambio", arguments: { fecha: "2026-10-07" } } }),
}), { DB });
const m = await mcp.json();
check("consultar_tipo_cambio por MCP", m.result?.structuredContent?.valor, 17.978);

if (contar()) {
  console.log(`\n${contar()} prueba(s) fallaron.`);
  process.exit(1);
}
console.log("\nTodas las pruebas pasaron.");
