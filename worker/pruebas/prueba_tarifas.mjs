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

console.log("\nPDBT: cargos reales de CFE (Noroeste, marzo 2026)");
r = await get("/v1/tarifa?tarifa=PDBT&estado=SONORA&municipio=NAVOJOA&anio=2026&mes=3");
check("status", r.status, 200);
check("tarifa y región", [r.cuerpo.tarifa, r.cuerpo.region], ["PDBT", "NOROESTE"]);
check("periodo de CFE", r.cuerpo.periodo_cfe, "MAR-26");
check("dos cargos: sin demanda ni horarios", r.cuerpo.cargos, { energia: 3.347, fijo: 19.78 });
check("unidades", r.cuerpo.unidades, { energia: "$/kWh", fijo: "$/mes" });
check("sin sistema_horario ni división de horario",
  ["sistema_horario" in r.cuerpo, "division" in r.cuerpo], [false, false]);
r = await get("/v1/tarifa?tarifa=PDBT&region=NOROESTE&anio=2025&mes=12");
check("el cambio de cargo fijo de enero de 2026 se ve (diciembre)", r.cuerpo.cargos, { energia: 3.435, fijo: 77.77 });
r = await get("/v1/tarifa?tarifa=PDBT&region=NOROESTE&anio=2026&mes=1");
check("el cambio de cargo fijo de enero de 2026 se ve (enero)", r.cuerpo.cargos, { energia: 3.345, fijo: 19.78 });
r = await get("/v1/tarifa?tarifa=PDBT&region=ORIENTE&anio=2026&mes=3");
check("PDBT en una región sin capturar: 404", r.status, 404);

console.log("\nDAC: se ubica por región de DAC, no por división");
r = await get("/v1/tarifa?tarifa=DAC&estado=SONORA&municipio=NAVOJOA&anio=2026&mes=9");
check("status", r.status, 200);
check("Navojoa (división NOROESTE, confirmada) cae en la región de DAC Noroeste", [r.cuerpo.region, r.cuerpo.via_region], ["NOROESTE", "division"]);
check("cargos de DAC Noroeste 2026-09", r.cuerpo.cargos, { energia: 6.143, fijo: 145.85 });
check("periodo", r.cuerpo.periodo_cfe, "SEP-26");
check("sin campos de horario", ["sistema_horario" in r.cuerpo, "division" in r.cuerpo], [false, false]);
check("advierte que el fijo de 2025-2026 no está validado", r.cuerpo.nota.includes("no está validado"), true);
check("trae el municipio consultado", [r.cuerpo.estado, r.cuerpo.municipio], ["SONORA", "NAVOJOA"]);

r = await get("/v1/tarifa?tarifa=DAC&region=NOROESTE&anio=2019&mes=9");
check("el recibo real de septiembre de 2019: precios del portal", r.cuerpo.cargos, { energia: 4.305, fijo: 107.74 });
check("y reproducen el importe de Energía del recibo (3,662 kWh): 15,872.65",
  Math.round((r.cuerpo.cargos.fijo + 3662 * r.cuerpo.cargos.energia) * 100) / 100, 15872.65);

r = await get("/v1/tarifa?tarifa=DAC&region=CENTRAL&anio=2026&mes=9");
check("una región de DAC pedida por nombre se usa tal cual", [r.cuerpo.region, r.cuerpo.via_region, r.cuerpo.cargos.energia],
  ["CENTRAL", "region_dac", 6.557]);
r = await get("/v1/tarifa?tarifa=DAC&region=BAJA%20CALIFORNIA&anio=2026&mes=9");
check("Baja California trae energía de verano y de fuera de verano", r.cuerpo.cargos,
  { energia_fuera_verano: 5.475, energia_verano: 6.376, fijo: 145.85 });
r = await get("/v1/tarifa?tarifa=DAC&region=norte%20y%20noreste&anio=2026&mes=9");
check("el nombre de región no distingue mayúsculas ni acentos", r.cuerpo.cargos.energia, 5.984);

console.log("\nDAC: una división sin mapeo confirmado no se adivina");
r = await get("/v1/tarifa?tarifa=DAC&estado=AGUASCALIENTES&municipio=AGUASCALIENTES&anio=2026&mes=9");
check("municipio de una división sin confirmar: 404", r.status, 404);
check("dice que no está confirmada y que no adivina", r.cuerpo.error.includes("no está confirmada"), true);
check("nombra la división", r.cuerpo.division, "BAJIO");
check("ofrece las regiones de DAC", r.cuerpo.regiones_dac.length, 6);
check("y las divisiones confirmadas", r.cuerpo.divisiones_confirmadas, ["NOROESTE"]);
r = await get("/v1/tarifa?tarifa=DAC&region=JALISCO&anio=2026&mes=9");
check("una división pedida por region= tampoco se adivina", [r.status, r.cuerpo.error.includes("no está confirmada")], [404, true]);
r = await get("/v1/tarifa?tarifa=DAC&region=NOEXISTE&anio=2026&mes=9");
check("un nombre que no es de DAC ni división", [r.status, r.cuerpo.error.includes("no es una región de DAC")], [404, true]);
r = await get("/v1/tarifa?tarifa=DAC&region=NOROESTE&anio=2024&mes=9");
check("DAC sin datos de ese año: 404 con lo que sí hay", [r.status, r.cuerpo.periodos_disponibles.includes("2025-01")], [404, true]);

console.log("\nLas regiones de DAC no contaminan las divisiones");
r = await get("/v1/regiones");
check("NORTE Y NORESTE no aparece como región", r.cuerpo.regiones.some((x) => x.region === "NORTE Y NORESTE"), false);
check("SUR Y PENINSULAR tampoco", r.cuerpo.regiones.some((x) => x.region === "SUR Y PENINSULAR"), false);
check("las divisiones de siempre siguen", r.cuerpo.regiones.some((x) => x.region === "NOROESTE"), true);

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
check("lista las tarifas disponibles", r.cuerpo.tarifas_disponibles, ["DAC", "GDMTH", "GDMTO", "PDBT"]);

console.log("\n/v1/tarifas");
r = await get("/v1/tarifas");
check("status", r.status, 200);
check("claves", r.cuerpo.tarifas.map((t) => t.tarifa), ["DAC", "GDMTH", "GDMTO", "PDBT"]);
const por = Object.fromEntries(r.cuerpo.tarifas.map((t) => [t.tarifa, t]));
const { GDMTH: h, GDMTO: o, PDBT: pd, DAC: dac } = por;
check("GDMTH tiene horarios y 17 regiones", [h.horarios, h.regiones.length], [true, 17]);
check("GDMTH desde 2018-01", h.periodo_desde, "2018-01");
check("GDMTO sin horarios", o.horarios, false);
check("GDMTO piloto: Noroeste y Oriente", o.regiones, ["NOROESTE", "ORIENTE"]);
check("GDMTO desde 2025-01", o.periodo_desde, "2025-01");
check("PDBT piloto: Noroeste, sin horarios, desde 2025-01",
  [pd.regiones, pd.horarios, pd.periodo_desde, pd.registros >= 21], [["NOROESTE"], false, "2025-01", true]);
check("PDBT con descripción", pd.descripcion.includes("Pequeña demanda"), true);
check("DAC: seis regiones de DAC, sin horarios, por región de DAC",
  [dac.regiones, dac.horarios, dac.ubicacion],
  [["BAJA CALIFORNIA", "BAJA CALIFORNIA SUR", "CENTRAL", "NOROESTE", "NORTE Y NORESTE", "SUR Y PENINSULAR"], false, "region_dac"]);
check("DAC incluye el registro de validación de 2019-09", dac.periodo_desde, "2019-09");
check("DAC: seis registros por mes", dac.registros >= 6 * 24, true);
check("DAC declara que el fijo de 2025-2026 no está validado", dac.notas.some((n) => n.includes("NO está validado")), true);
check("DAC declara que solo Noroeste está confirmada", dac.notas.some((n) => n.includes("Solo la división NOROESTE")), true);
check("las demás tarifas no llevan notas", [h.notas, o.notas, pd.notas], [undefined, undefined, undefined]);
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
