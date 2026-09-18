/**
 * Pruebas de la API REST, sin desplegar nada.
 *
 *   cd worker && node pruebas/prueba_api.mjs
 *
 * Las pruebas del servidor MCP viven aparte, en prueba_mcp.mjs, para que
 * cada archivo se pueda correr y leer por separado.
 */
import { BASE, crearVerificador, crearWorker } from "./_entorno.mjs";

const worker = await crearWorker();
const { check, contar } = crearVerificador();

const get = async (ruta) => {
  const r = await worker.fetch(new Request(BASE + ruta));
  const cuerpo = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  return { status: r.status, cuerpo };
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

// 2010 es un año "válido" (dentro del rango de cordura) pero anterior al
// histórico real de CFE, así que nunca va a tener datos capturados.
r = await get("/v1/tarifa?region=NOROESTE&anio=2010&mes=7");
check("mes sin capturar da 404", r.status, 404);
check("404 dice qué periodos sí hay", Array.isArray(r.cuerpo.periodos_disponibles), true);

r = await get("/v1/tarifa?estado=SONORA&municipio=MUNICIPIO INVENTADO&anio=2026&mes=3");
check("municipio fuera del catálogo da 404", r.status, 404);

r = await get("/v1/tarifa?region=NOROESTE&anio=2026&mes=13");
check("mes inválido", r.cuerpo.error.includes("1 a 12"), true);

r = await get("/v1/tarifa?region=NOROESTE&anio=99999&mes=3");
check("año fuera de rango da error claro", r.cuerpo.error.includes("cuatro dígitos"), true);

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

r = await get("/v1/horarios?region=NOROESTE&fecha=2026-01-15&hora=25:99");
check("hora fuera de rango da error claro", r.cuerpo.error.includes("00:00 y 23:59"), true);

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
check("los endpoints van como enlaces reales, no como texto",
  r.cuerpo.includes('<a href="https://ejemplo.workers.dev/v1/regiones">'), true);
check("la portada enlaza el llms.txt",
  r.cuerpo.includes('href="https://ejemplo.workers.dev/llms.txt"'), true);
r = await get("/llms.txt");
check("llms.txt responde", r.status, 200);
check("es markdown, no HTML", r.cuerpo.startsWith("# API de tarifas"), true);
check("trae las URL completas", r.cuerpo.includes("https://ejemplo.workers.dev/v1/tarifa?"), true);
check("documenta el endpoint MCP", r.cuerpo.includes("/mcp"), true);
check("advierte del caso de varias divisiones", r.cuerpo.includes("más de una división"), true);
r = await get("/robots.txt");
check("robots.txt permite el rastreo", r.cuerpo.includes("Allow: /"), true);
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

console.log("\nCORS");
const pre = await worker.fetch(new Request(BASE + "/v1/regiones", { method: "OPTIONS" }));
check("CORS preflight", pre.status, 204);
check("CORS abierto", pre.headers.get("access-control-allow-origin"), "*");
check("MCP-Protocol-Version queda expuesto para clientes en navegador",
  pre.headers.get("access-control-expose-headers")?.includes("mcp-protocol-version"), true);

console.log();
if (contar()) {
  console.log(`${contar()} prueba(s) fallaron.`);
  process.exit(1);
}
console.log("Todas las pruebas pasaron.");
