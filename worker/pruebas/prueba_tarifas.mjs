/**
 * Pruebas de la oferta de tarifas: GDMTO, el catálogo /v1/tarifas y que GDMTH
 * siga respondiendo exactamente igual.
 *
 *   cd worker && node pruebas/prueba_tarifas.mjs
 *
 * Corren sobre una copia de data/, que incluye lo capturado de verdad.
 */
import { BASE, crearVerificador, crearWorker } from "./_entorno.mjs";

const worker = await crearWorker();
const { check, contar } = crearVerificador();

const get = async (ruta) => {
  const r = await worker.fetch(new Request(BASE + ruta));
  return { status: r.status, cuerpo: await r.json() };
};

console.log("GDMTO: cargos reales de CFE (Noroeste, septiembre 2026)");
let r = await get("/v1/tarifa?tarifa=GDMTO&estado=SONORA&municipio=NAVOJOA&anio=2026&mes=9");
check("status", r.status, 200);
check("tarifa", r.cuerpo.tarifa, "GDMTO");
check("región resuelta desde el municipio", r.cuerpo.region, "NOROESTE");
check("periodo de CFE", r.cuerpo.periodo_cfe, "SEP-26");
check("cuatro cargos, sin horarios ni demanda por punta", r.cuerpo.cargos,
  { capacidad: 327.96, distribucion: 90.85, energia: 1.261, fijo: 197.77 });
check("unidades", r.cuerpo.unidades,
  { capacidad: "$/kW", distribucion: "$/kW", energia: "$/kWh", fijo: "$/mes" });
check("conceptos con la forma de siempre", r.cuerpo.conceptos[1],
  { cargo: "Variable (Energía)", int_horario: "-", unidades: "$/kWh", valor: 1.261 });
check("sin sistema_horario (no le aplica)", "sistema_horario" in r.cuerpo, false);
check("sin división de horario", "division" in r.cuerpo, false);
check("trae fuente de GDMTO", r.cuerpo.fuente.includes("GranDemandaMTO"), true);
check("trae aviso", typeof r.cuerpo.aviso, "string");

console.log("\nGDMTO en Oriente (cargos reales de CFE, septiembre 2026)");
r = await get("/v1/tarifa?tarifa=GDMTO&region=ORIENTE&anio=2026&mes=9");
check("Oriente 2026-09", r.cuerpo.cargos,
  { capacidad: 279.94, distribucion: 202.45, energia: 1.282, fijo: 636.28 });
r = await get("/v1/tarifa?tarifa=GDMTO&region=ORIENTE&anio=2025&mes=10");
check("Oriente 2025-10 (antes del cambio de enero de 2026)", r.cuerpo.cargos,
  { capacidad: 323.18, distribucion: 211.58, energia: 1.453, fijo: 474.54 });

r = await get("/v1/tarifa?tarifa=gdmto&region=noroeste&anio=2026&mes=9");
check("clave de tarifa y región sin importar mayúsculas", r.cuerpo.cargos.capacidad, 327.96);

console.log("\nGDMTH sigue igual");
r = await get("/v1/tarifa?estado=SONORA&municipio=NAVOJOA&anio=2026&mes=3");
check("cargos de GDMTH", r.cuerpo.cargos, {
  base: 0.9715, capacidad: 392.66, distribucion: 90.85,
  fijo: 197.77, intermedia: 1.5573, punta: 1.7262,
});
check("GDMTH conserva sistema_horario", "sistema_horario" in r.cuerpo, true);
check("GDMTH conserva división", r.cuerpo.division, "NOROESTE");

console.log("\nCasos de error");
r = await get("/v1/tarifa?tarifa=GDMTO&region=NORTE&anio=2026&mes=9");
check("GDMTO en una región sin capturar: 404", r.status, 404);
check("lo dice con la región", r.cuerpo.error.includes("GDMTO en NORTE"), true);
check("y sin periodos disponibles", r.cuerpo.periodos_disponibles, []);

r = await get("/v1/tarifa?tarifa=NOEXISTE&region=NOROESTE&anio=2026&mes=9");
check("tarifa desconocida: 404", r.status, 404);
check("lista las tarifas disponibles", r.cuerpo.tarifas_disponibles, ["GDMTH", "GDMTO"]);

console.log("\n/v1/tarifas");
r = await get("/v1/tarifas");
check("status", r.status, 200);
check("claves", r.cuerpo.tarifas.map((t) => t.tarifa), ["GDMTH", "GDMTO"]);
const [h, o] = r.cuerpo.tarifas;
check("GDMTH tiene horarios y 17 regiones", [h.horarios, h.regiones.length], [true, 17]);
check("GDMTH desde 2018-01", h.periodo_desde, "2018-01");
check("GDMTO sin horarios", o.horarios, false);
check("GDMTO piloto: Noroeste y Oriente", o.regiones, ["NOROESTE", "ORIENTE"]);
check("GDMTO desde 2025-01", o.periodo_desde, "2025-01");
check("GDMTO llega al menos a 2026-09", o.periodo_hasta >= "2026-09", true);
check("registros de GDMTO = meses de las dos regiones", o.registros >= 42, true);
check("explica qué es el mes", r.cuerpo.nota_mes.includes("sin ajustes"), true);
check("OpenAPI lo documenta",
  Object.keys((await get("/openapi.json")).cuerpo.paths).includes("/v1/tarifas"), true);

console.log();
if (contar()) {
  console.log(`${contar()} prueba(s) fallaron.`);
  process.exit(1);
}
console.log("Todas las pruebas pasaron.");
