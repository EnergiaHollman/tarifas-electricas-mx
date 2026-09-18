/**
 * Pruebas del Worker sin desplegar nada.
 *
 *   cd worker && node pruebas/prueba_api.mjs
 *
 * Empaqueta src/ con esbuild y le manda Requests reales al handler. Node 22
 * ya trae Request y Response, así que no hace falta simular nada.
 */
import { build } from "esbuild";
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
// En Windows, import() exige una URL file://; una ruta absoluta "C:\..." falla.
import { pathToFileURL } from "node:url";

const dir = mkdtempSync(path.join(tmpdir(), "worker-"));

// Se trabaja sobre una copia: las pruebas inyectan datos de ejemplo para
// cubrir casos que la semilla no trae, y eso nunca debe tocar data/ real.
cpSync("src", path.join(dir, "worker", "src"), { recursive: true });
cpSync("../data", path.join(dir, "data"), { recursive: true });

const rutaDatos = (n) => path.join(dir, "data", n);
const leer = (n) => JSON.parse(readFileSync(rutaDatos(n), "utf8"));
const escribir = (n, d) => writeFileSync(rutaDatos(n), JSON.stringify(d, null, 1));

// Municipio que CFE atiende con dos divisiones tarifarias.
const cat = leer("catalogo.json");
cat.expansiones = {
  "BAJIO Y GOLFO CENTRO": ["BAJIO", "GOLFO CENTRO"],
  // El prefijo elidido: no se podría deducir partiendo el texto.
  "VALLE DE MEXICO CENTRO Y SUR": ["VALLE DE MEXICO CENTRO", "VALLE DE MEXICO SUR"],
};
cat.estados["GUANAJUATO"] = {
  id: "11", nombre: "GUANAJUATO",
  municipios: {
    "SAN LUIS DE LA PAZ": {
      id: "999901", nombre: "SAN LUIS DE LA PAZ",
      opciones: [{ id: "99", etiqueta: "BAJIO Y GOLFO CENTRO" }],
    },
    // Municipio con dos opciones separadas en el desplegable.
    "CELAYA": {
      id: "999902", nombre: "CELAYA",
      opciones: [
        { id: "1", etiqueta: "BAJIO" },
        { id: "2", etiqueta: "GOLFO CENTRO" },
      ],
    },
  },
};
escribir("catalogo.json", cat);

const tar = leer("tarifas.json");
const base = tar.registros["GDMTH|NOROESTE|2026-03"];
for (const [reg, punta] of [["BAJIO", 1.5], ["GOLFO CENTRO", 1.6]]) {
  const rec = JSON.parse(JSON.stringify(base));
  rec.region = reg;
  rec.cargos.punta = punta;
  rec.municipio_consultado = "SAN LUIS DE LA PAZ, GUANAJUATO";
  tar.registros[`GDMTH|${reg}|2026-03`] = rec;
}
escribir("tarifas.json", tar);

const salida = path.join(dir, "bundle.mjs");
await build({
  entryPoints: [path.join(dir, "worker", "src", "index.ts")],
  bundle: true,
  format: "esm",
  platform: "neutral",
  outfile: salida,
  logLevel: "warning",
});
const worker = (await import(pathToFileURL(salida).href)).default;

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

const BASE = "https://ejemplo.workers.dev";
const get = async (ruta) => {
  const r = await worker.fetch(new Request(BASE + ruta));
  const cuerpo = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  return { status: r.status, cuerpo };
};
const rpc = async (metodo, params, id = 1) => {
  const r = await worker.fetch(
    new Request(BASE + "/mcp", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id, method: metodo, params }),
    }),
  );
  return { status: r.status, cuerpo: r.status === 202 ? null : await r.json() };
};

console.log("REST: cargos");
let r = await get("/v1/tarifa?estado=SONORA&municipio=NAVOJOA&anio=2026&mes=3");
check("status", r.status, 200);
check("región resuelta desde el municipio", r.cuerpo.region, "NOROESTE");
check("cargos", r.cuerpo.cargos, {
  base: 0.9715, capacidad: 392.66, distribucion: 90.85,
  fijo: 197.77, intermedia: 1.5573, punta: 1.7262,
});
check("unidades de energía", r.cuerpo.unidades.punta, "$/kWh");
check("trae fuente", typeof r.cuerpo.fuente, "string");
check("trae fecha de captura", typeof r.cuerpo.fecha_captura, "string");
check("trae aviso", r.cuerpo.aviso.includes("no es un servicio oficial") ||
  r.cuerpo.aviso.includes("no es un servicio oficial de CFE") ||
  r.cuerpo.aviso.length > 50, true);

r = await get("/v1/tarifa?region=NOROESTE&anio=2026&mes=3");
check("consulta por región directa", r.cuerpo.cargos.punta, 1.7262);

r = await get("/v1/tarifa?region=NOROESTE&anio=1999&mes=7");
check("mes sin capturar da 404", r.status, 404);
check("404 dice qué periodos sí hay", Array.isArray(r.cuerpo.periodos_disponibles), true);

r = await get("/v1/tarifa?estado=SONORA&municipio=MUNICIPIO INVENTADO&anio=2026&mes=3");
check("municipio fuera del catálogo da 404", r.status, 404);

r = await get("/v1/tarifa?region=NOROESTE&anio=2026&mes=13");
check("mes inválido", r.cuerpo.error.includes("1 a 12"), true);

r = await get("/v1/tarifa?anio=2026&mes=3");
check("sin ubicación", r.cuerpo.error.includes("Falta la ubicación"), true);

console.log("\nREST: horarios y calendario");
// 15 de agosto de 2026 es sábado, en verano.
r = await get("/v1/horarios?region=NOROESTE&fecha=2026-08-15&hora=20:30");
check("status", r.status, 200);
check("temporada", r.cuerpo.temporada, "verano");
check("tipo de día", r.cuerpo.tipo_dia, "sabado");
check("sábado de verano no tiene punta", r.cuerpo.franjas.some((f) => f.periodo === "punta"), false);
check("20:30 del sábado cae en intermedia", r.cuerpo.consulta.periodo, "intermedia");

// 15 de enero de 2026 es jueves, invierno.
r = await get("/v1/horarios?region=NOROESTE&fecha=2026-01-15&hora=20:30");
check("temporada invierno", r.cuerpo.temporada, "invierno");
check("día hábil", r.cuerpo.tipo_dia, "habil");
check("20:30 hábil de invierno es punta", r.cuerpo.consulta.periodo, "punta");
check("franjas de invierno hábil", r.cuerpo.franjas, [
  { periodo: "base", inicio: "00:00", fin: "06:00" },
  { periodo: "intermedia", inicio: "06:00", fin: "18:00" },
  { periodo: "punta", inicio: "18:00", fin: "22:00" },
  { periodo: "intermedia", inicio: "22:00", fin: "24:00" },
]);

// 5 de febrero de 2026 cae en jueves; el festivo es el primer lunes, el 2.
r = await get("/v1/horarios?region=NOROESTE&fecha=2026-02-02");
check("festivo de febrero se trata como domingo", r.cuerpo.tipo_dia, "domingo");
r = await get("/v1/horarios?region=NOROESTE&fecha=2026-02-05");
check("el 5 de febrero es día hábil", r.cuerpo.tipo_dia, "habil");

// Frontera de temporada 2026: primer domingo de abril = 5 de abril.
r = await get("/v1/horarios?region=NOROESTE&fecha=2026-04-04");
check("4 de abril todavía es invierno", r.cuerpo.temporada, "invierno");
r = await get("/v1/horarios?region=NOROESTE&fecha=2026-04-05");
check("5 de abril ya es verano", r.cuerpo.temporada, "verano");
// Último domingo de octubre 2026 = 25; el verano termina el sábado 24.
r = await get("/v1/horarios?region=NOROESTE&fecha=2026-10-24");
check("24 de octubre es el último día de verano", r.cuerpo.temporada, "verano");
r = await get("/v1/horarios?region=NOROESTE&fecha=2026-10-25");
check("25 de octubre ya es invierno", r.cuerpo.temporada, "invierno");

// Baja California tiene calendario propio: verano arranca el 1 de mayo.
r = await get("/v1/horarios?region=BAJA CALIFORNIA&fecha=2026-04-20");
check("BC en abril es invierno", r.cuerpo.temporada, "invierno");
r = await get("/v1/horarios?region=BAJA CALIFORNIA&fecha=2026-05-01");
check("BC el 1 de mayo es verano", r.cuerpo.temporada, "verano");
check("BC usa su propia zona", r.cuerpo.zona, "Región Baja California");

console.log("\nREST: catálogos y varios");
r = await get("/v1/regiones");
check("lista regiones", r.cuerpo.regiones.some((x) => x.region === "NOROESTE"), true);
r = await get("/v1/estados");
check("lista estados", r.cuerpo.estados.includes("SONORA"), true);
r = await get("/v1/municipios?estado=sonora");
check("municipios ignora mayúsculas y acentos",
  r.cuerpo.municipios.some((m) => m.nombre === "NAVOJOA" && m.region === "NOROESTE"), true);
r = await get("/v1/salud");
check("salud", r.cuerpo.ok, true);
r = await get("/openapi.json");
check("openapi", r.cuerpo.openapi, "3.1.0");
r = await get("/");
check("portada es HTML", r.cuerpo.startsWith("<!doctype html>"), true);
r = await get("/no-existe");
check("404 de ruta", r.status, 404);

console.log("\nMunicipios que CFE atiende con dos divisiones");
r = await get("/v1/tarifa?estado=GUANAJUATO&municipio=SAN LUIS DE LA PAZ&anio=2026&mes=3");
check("status", r.status, 200);
check("devuelve las dos regiones", r.cuerpo.regiones, ["BAJIO", "GOLFO CENTRO"]);
check("un resultado por región", r.cuerpo.resultados.map((x) => x.region),
  ["BAJIO", "GOLFO CENTRO"]);
check("cada uno con sus cargos", r.cuerpo.resultados[0].cargos.punta, 1.5);
check("advierte de la ambigüedad",
  r.cuerpo.nota.includes("más de una división"), true);
r = await get("/v1/tarifa?estado=GUANAJUATO&municipio=CELAYA&anio=2026&mes=3");
check("municipio con dos opciones del desplegable", r.cuerpo.regiones,
  ["BAJIO", "GOLFO CENTRO"]);
r = await get("/v1/regiones");
check("no aparece una región falsa por partir texto",
  r.cuerpo.regiones.some((x) => x.region === "SUR"), false);
check("las dos aparecen en el listado",
  ["BAJIO", "GOLFO CENTRO"].every((x) => r.cuerpo.regiones.some((y) => y.region === x)), true);

console.log("\nMCP");
r = await rpc("initialize", { protocolVersion: "2025-06-18" });
check("initialize", r.cuerpo.result.serverInfo.name, "tarifas-electricas-mx");
check("anuncia tools", "tools" in r.cuerpo.result.capabilities, true);
r = await rpc("tools/list", {});
check("3 herramientas", r.cuerpo.result.tools.map((t) => t.name),
  ["consultar_tarifa", "consultar_horarios", "listar_regiones"]);
r = await rpc("tools/call", {
  name: "consultar_tarifa",
  arguments: { estado: "SONORA", municipio: "NAVOJOA", anio: 2026, mes: 3 },
});
check("tools/call devuelve cargos", r.cuerpo.result.structuredContent.cargos.punta, 1.7262);
check("tools/call no marca error", r.cuerpo.result.isError, false);
r = await rpc("tools/call", {
  name: "consultar_horarios",
  arguments: { region: "NOROESTE", fecha: "2026-01-15", hora: "20:30" },
});
check("horarios por MCP", r.cuerpo.result.structuredContent.consulta.periodo, "punta");
r = await rpc("tools/call", { name: "inventada", arguments: {} });
check("herramienta desconocida marca isError", r.cuerpo.result.isError, true);
r = await rpc("notifications/initialized", {});
check("notificación responde 202 sin cuerpo", r.status, 202);
r = await rpc("metodo/raro", {});
check("método no soportado", r.cuerpo.error.code, -32601);

const pre = await worker.fetch(new Request(BASE + "/v1/regiones", { method: "OPTIONS" }));
check("CORS preflight", pre.status, 204);
check("CORS abierto", pre.headers.get("access-control-allow-origin"), "*");

console.log();
if (fallos) {
  console.log(`${fallos} prueba(s) fallaron.`);
  process.exit(1);
}
console.log("Todas las pruebas pasaron.");
