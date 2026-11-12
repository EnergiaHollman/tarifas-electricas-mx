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

const v = async (q) => (await get("/v1/tarifa?" + q)).cuerpo;

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
r = await get("/v1/tarifa?tarifa=PDBT&region=ORIENTE&anio=2024&mes=3");
check("PDBT en un mes sin capturar (antes de la ventana): 404", r.status, 404);

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
check("NACIONAL (domésticas) tampoco", r.cuerpo.regiones.some((x) => x.region === "NACIONAL"), false);

console.log("\nDomésticas: precio nacional, escalones y temporada explícita");
r = await get("/v1/tarifa?tarifa=1&anio=2026&mes=9");
check("tarifa 1, sin ubicación ni temporada", r.status, 200);
check("cargos (publicados por CFE)", r.cuerpo.cargos, { basico: 1.136, excedente: 4.041, intermedio: 1.381 });
check("escalones en kWh: 75, luego 65 más, luego sin tope", r.cuerpo.escalones.map((e) => [e.nombre, e.desde_kwh, e.hasta_kwh, e.valor]),
  [["basico", 0, 75, 1.136], ["intermedio", 75, 140, 1.381], ["excedente", 140, null, 4.041]]);
check("mínimo mensual y periodo de facturación", [r.cuerpo.minimo_mensual_kwh, r.cuerpo.periodo_facturacion], [25, "mensual"]);
check("sin temporada ni región de división", ["temporada" in r.cuerpo, "sistema_horario" in r.cuerpo, r.cuerpo.region], [false, false, "NACIONAL"]);
check("la nota avisa de la facturación bimestral y de los apoyos",
  r.cuerpo.nota.includes("bimestral") && r.cuerpo.nota.includes("subsidios"), true);
r = await get("/v1/tarifa?tarifa=1&estado=SONORA&municipio=NAVOJOA&anio=2026&mes=9");
check("la ubicación se ignora (precio nacional)", r.cuerpo.cargos.basico, 1.136);

r = await get("/v1/tarifa?tarifa=1F&anio=2026&mes=9&inicio_verano=5");
check("1F, septiembre con inicio en mayo: verano", [r.status, r.cuerpo.temporada, r.cuerpo.inicio_verano], [200, "verano", 5]);
check("verano de 1F: cuatro escalones, 300 / 900 / 1300 kWh", r.cuerpo.escalones.map((e) => [e.nombre, e.desde_kwh, e.hasta_kwh, e.valor]),
  [["basico", 0, 300, 0.851], ["intermedio_bajo", 300, 1200, 1.051], ["intermedio_alto", 1200, 2500, 2.558], ["excedente", 2500, null, 4.041]]);
r = await get("/v1/tarifa?tarifa=1F&anio=2026&mes=9&inicio_verano=2");
check("1F, septiembre con inicio en febrero: fuera de verano", [r.cuerpo.temporada, r.cuerpo.cargos],
  ["fuera_verano", { basico: 1.136, excedente: 4.041, intermedio: 1.381 }]);
check("fuera de verano de 1F: tres escalones, 75 / 125 kWh", r.cuerpo.escalones.map((e) => [e.nombre, e.desde_kwh, e.hasta_kwh]),
  [["basico", 0, 75], ["intermedio", 75, 200], ["excedente", 200, null]]);
r = await get("/v1/tarifa?tarifa=1f&anio=2026&mes=9&inicio_verano=4");
check("septiembre con inicio en abril: verano (abril a septiembre)", r.cuerpo.temporada, "verano");
r = await get("/v1/tarifa?tarifa=1A&anio=2026&mes=9&inicio_verano=3");
check("septiembre con inicio en marzo: fuera de verano (marzo a agosto)", r.cuerpo.temporada, "fuera_verano");
r = await get("/v1/tarifa?tarifa=1A&anio=2026&mes=9&temporada=verano");
check("temporada explícita en lugar del inicio", [r.cuerpo.temporada, r.cuerpo.cargos.basico, "inicio_verano" in r.cuerpo], ["verano", 1.016, false]);
r = await get("/v1/tarifa?tarifa=1A&anio=2026&mes=9&temporada=fuera%20de%20verano");
check("temporada con espacios y mayúsculas", r.cuerpo.temporada, "fuera_verano");
r = await get("/v1/tarifa?tarifa=1A&anio=2026&mes=9&inicio_verano=4&temporada=verano");
check("inicio y temporada coherentes", r.cuerpo.temporada, "verano");

console.log("\nDomésticas: lo que no se infiere ni se adivina");
r = await get("/v1/tarifa?tarifa=1B&anio=2026&mes=9");
check("sin inicio_verano ni temporada: error que lo pide", [r.status, r.cuerpo.error.includes("inicio_verano")], [404, true]);
r = await get("/v1/tarifa?tarifa=1B&anio=2026&mes=9&inicio_verano=4&temporada=fuera_verano");
check("inicio y temporada que se contradicen", [r.status, r.cuerpo.error.includes("se contradicen")], [404, true]);
r = await get("/v1/tarifa?tarifa=1B&anio=2026&mes=9&inicio_verano=9");
check("inicio fuera de 2 a 5", [r.status, r.cuerpo.error.includes("de 2 (febrero) a 5 (mayo)")], [404, true]);
r = await get("/v1/tarifa?tarifa=1B&anio=2026&mes=9&temporada=invierno");
check("temporada desconocida", [r.status, r.cuerpo.error.includes("verano")], [404, true]);
r = await get("/v1/tarifa?tarifa=1B&anio=2026&mes=1&temporada=verano");
check("enero no tiene verano con los inicios que ofrece CFE: lo dice", [r.status, r.cuerpo.temporadas_disponibles], [404, ["fuera_verano"]]);
r = await get("/v1/tarifa?tarifa=1B&anio=2026&mes=1&inicio_verano=2");
check("enero con cualquier inicio: fuera de verano", r.cuerpo.temporada, "fuera_verano");
r = await get("/v1/tarifa?tarifa=1B&anio=2024&mes=9&inicio_verano=2");
check("doméstica sin datos de ese año: 404 con lo que sí hay", [r.status, r.cuerpo.periodos_disponibles.includes("2025-01")], [404, true]);

console.log("\nGDMTH sigue igual");
r = await get("/v1/tarifa?estado=SONORA&municipio=NAVOJOA&anio=2026&mes=3");
check("cargos de GDMTH", r.cuerpo.cargos, {
  base: 0.9715, capacidad: 392.66, distribucion: 90.85,
  fijo: 197.77, intermedia: 1.5573, punta: 1.7262,
});
check("GDMTH conserva sistema_horario", "sistema_horario" in r.cuerpo, true);
check("GDMTH conserva división", r.cuerpo.division, "NOROESTE");

console.log("\nCasos de error");
r = await get("/v1/tarifa?tarifa=GDMTO&region=NORTE&anio=2024&mes=9");
check("GDMTO en un mes sin capturar (antes de la ventana): 404", r.status, 404);
check("lo dice con la región", r.cuerpo.error.includes("GDMTO en NORTE"), true);
check("y da los periodos que sí hay: 2025-09 a 2026-10", [r.cuerpo.periodos_disponibles[0], r.cuerpo.periodos_disponibles.at(-1)], ["2025-09", "2026-10"]);

r = await get("/v1/tarifa?tarifa=NOEXISTE&region=NOROESTE&anio=2026&mes=9");
check("tarifa desconocida: 404", r.status, 404);
check("lista las tarifas disponibles", r.cuerpo.tarifas_disponibles,
  ["1", "1A", "1B", "1C", "1D", "1E", "1F", "DAC", "GDMTH", "GDMTO", "PDBT"]);

console.log("\n/v1/tarifas");
r = await get("/v1/tarifas");
check("status", r.status, 200);
check("claves", r.cuerpo.tarifas.map((t) => t.tarifa),
  ["1", "1A", "1B", "1C", "1D", "1E", "1F", "DAC", "GDMTH", "GDMTO", "PDBT"]);
const por = Object.fromEntries(r.cuerpo.tarifas.map((t) => [t.tarifa, t]));
const { GDMTH: h, GDMTO: o, PDBT: pd, DAC: dac } = por;
check("GDMTH tiene horarios y 17 regiones", [h.horarios, h.regiones.length], [true, 17]);
check("GDMTH desde 2018-01", h.periodo_desde, "2018-01");
check("GDMTO sin horarios", o.horarios, false);
check("GDMTO: las 17 divisiones", [o.regiones.length, o.regiones.includes("SURESTE")], [17, true]);
check("GDMTO desde 2025-01", o.periodo_desde, "2025-01");
check("PDBT: las 17 divisiones, sin horarios, desde 2025-01 (Noroeste conserva sus meses previos)",
  [pd.regiones.length, pd.horarios, pd.periodo_desde, pd.registros >= 17 * 14], [17, false, "2025-01", true]);
check("PDBT con descripción", pd.descripcion.includes("Pequeña demanda"), true);
check("DAC: seis regiones de DAC, sin horarios, por región de DAC",
  [dac.regiones, dac.horarios, dac.ubicacion],
  [["BAJA CALIFORNIA", "BAJA CALIFORNIA SUR", "CENTRAL", "NOROESTE", "NORTE Y NORESTE", "SUR Y PENINSULAR"], false, "region_dac"]);
check("DAC incluye el registro de validación de 2019-09", dac.periodo_desde, "2019-09");
check("DAC: seis registros por mes", dac.registros >= 6 * 24, true);
check("DAC declara que el fijo de 2025-2026 no está validado", dac.notas.some((n) => n.includes("NO está validado")), true);
check("domésticas: precio nacional, por escalones",
  ["1", "1A", "1B", "1C", "1D", "1E", "1F"].map((c) => [por[c].ubicacion, por[c].regiones, por[c].horarios, por[c].periodo_desde]),
  [...Array(6).fill(["nacional", ["NACIONAL"], false, "2025-01"]), ["nacional", ["NACIONAL"], false, "2023-02"]]);
// 1F incluye 2023-02 a 2023-04 (capturas puntuales para contrastar un recibo), como DAC incluye 2019-09.
check("1F: 2023-02..04 son capturas puntuales y la nota lo dice",
  por["1F"].notas.some((n) => n.includes("la cobertura continua de 1F empieza en 2025-01")), true);
check("las domésticas con temporada piden inicio_verano o temporada; la 1 no",
  [por["1"].parametros.includes("inicio_verano"), por["1A"].parametros.includes("inicio_verano")], [false, true]);
check("las domésticas avisan que los apoyos no están y que los límites son mensuales",
  por["1F"].notas.some((n) => n.includes("subsidios")) && por["1F"].notas.some((n) => n.includes("MENSUALES")), true);
check("la 1 no menciona temporada en sus notas", por["1"].notas.some((n) => n.includes("inicio_verano")), false);
check("DAC declara que solo Noroeste está confirmada", dac.notas.some((n) => n.includes("Solo la división NOROESTE")), true);
check("GDMTH no lleva notas", h.notas, undefined);
check("GDMTO explica energia_4dec y validado", o.notas.length === 2 && o.notas[0].includes("energia_4dec") && o.notas[1].includes("validado"), true);
check("PDBT explica energia_4dec y validado", pd.notas.length === 2 && pd.notas[0].includes("energia_4dec") && pd.notas[1].includes("sin recibo reproducido"), true);
check("GDMTO llega al menos a 2026-09", o.periodo_hasta >= "2026-09", true);
check("registros de GDMTO = meses de las dos regiones", o.registros >= 42, true);
check("explica qué es el mes", r.cuerpo.nota_mes.includes("sin ajustes"), true);
check("OpenAPI lo documenta",
  Object.keys((await get("/openapi.json")).cuerpo.paths).includes("/v1/tarifas"), true);

console.log("\nGDMTO: energía con 4 decimales (suma de componentes del aviso del DOF)");
r = await get("/v1/tarifa?tarifa=GDMTO&region=ORIENTE&anio=2026&mes=9");
check("energia del portal, sin cambios", r.cuerpo.cargos.energia, 1.282);
check("energia_4dec = suma de los cuatro cargos", r.cuerpo.energia_4dec, 1.2816);
check("componentes del DOF",  r.cuerpo.componentes_energia,
  { transmision: 0.1801, cenace: 0.0076, suministro: 0.0069, generacion: 1.087 });
check("precisión declarada", r.cuerpo.energia_precision, "dof_4_decimales");
check("trae el aviso del DOF", r.cuerpo.aviso_dof, 5800039);
r = await get("/v1/tarifa?tarifa=GDMTO&region=ORIENTE&anio=2026&mes=5");
check("mayo de 2026 (aviso 5788863)", [r.cuerpo.cargos.energia, r.cuerpo.energia_4dec], [1.315, 1.3146]);
r = await get("/v1/tarifa?tarifa=GDMTO&region=ORIENTE&anio=2025&mes=9");
check("septiembre de 2025", r.cuerpo.energia_4dec, 1.4527);
r = await get("/v1/tarifa?tarifa=GDMTO&region=NOROESTE&anio=2026&mes=9");
check("Noroeste también", r.cuerpo.energia_4dec, 1.2606);
r = await get("/v1/tarifa?tarifa=GDMTO&region=ORIENTE&anio=2026&mes=11");
check("sin aviso del mes: energia_4dec null, no inventado", [r.cuerpo.energia_4dec, r.cuerpo.componentes_energia], [null, null]);
check("sin aviso: se marca de 3 decimales y energia sigue siendo la del portal",
  [r.cuerpo.energia_precision, r.cuerpo.cargos.energia, "aviso_dof" in r.cuerpo], ["portal_3_decimales", 1.282, false]);
r = await get("/v1/tarifa?tarifa=GDMTH&region=ORIENTE&anio=2026&mes=9");
check("GDMTH no cambia: sin campos nuevos",
  ["energia_4dec", "energia_precision", "componentes_energia", "aviso_dof"].some((k) => k in r.cuerpo), false);

console.log("\nPDBT: energía con 4 decimales (suma de seis cargos del aviso del DOF)");
const esperadoPdbt = { // valores del DOF, Noroeste; los reproduce Dashboard con sus recibos (Tepeyac)
  "2025-01": 3.5528, "2025-02": 3.5568, "2025-03": 3.5578, "2025-06": 3.6188, "2025-07": 3.6578,
  "2025-08": 3.6618, "2025-09": 3.6409, "2025-10": 3.6409, "2025-11": 3.5619, "2025-12": 3.4349,
  "2026-01": 3.3449, "2026-03": 3.3469, "2026-05": 3.3239, "2026-07": 3.2539, "2026-10": 3.2539,
};
const obtenidoPdbt = {};
for (const periodo of Object.keys(esperadoPdbt)) {
  const [a, m] = periodo.split("-");
  obtenidoPdbt[periodo] = (await v(`tarifa=PDBT&region=NOROESTE&anio=${a}&mes=${Number(m)}`)).energia_4dec;
}
check("PDBT Noroeste: energia_4dec por mes = aviso del DOF (incluye 3.5578 de marzo de 2025)", obtenidoPdbt, esperadoPdbt);
r = await v("tarifa=PDBT&region=NOROESTE&anio=2026&mes=3");
check("PDBT: energia del portal sin cambios", r.cargos, { energia: 3.347, fijo: 19.78 });
check("PDBT: componentes fijos de 2026 (transmisión, distribución, CENACE, suministro)",
  [r.componentes_energia.transmision, r.componentes_energia.distribucion, r.componentes_energia.cenace, r.componentes_energia.suministro],
  [0.1801, 0.7753, 0.0076, 0.0069]);
check("PDBT: precisión y aviso", [r.energia_precision, typeof r.aviso_dof], ["dof_4_decimales", "number"]);
check("PDBT: la suma de los seis componentes es energia_4dec",
  Math.round(Object.values(r.componentes_energia).reduce((x, y) => x + y, 0) * 1e4) / 1e4, r.energia_4dec);
check("PDBT: seis componentes", Object.keys(r.componentes_energia).sort(),
  ["capacidad", "cenace", "distribucion", "generacion", "suministro", "transmision"]);
for (const [a, m] of [[2025, 4], [2025, 5]]) {
  const x = await v(`tarifa=PDBT&region=NOROESTE&anio=${a}&mes=${m}`);
  check(`PDBT Noroeste ${a}-0${m} (aviso no encontrado): null, portal_3_decimales y sin validar`,
    [x.energia_4dec, x.energia_precision, x.validado], [null, "portal_3_decimales", []]);
}
r = await v("tarifa=PDBT&region=NOROESTE&anio=2026&mes=11");
check("PDBT Noroeste 2026-11 (sin aviso todavía): null y portal_3_decimales", [r.energia_4dec, r.energia_precision], [null, "portal_3_decimales"]);
r = await v("tarifa=PDBT&region=ORIENTE&anio=2025&mes=3");
check("PDBT en otra división fuera de la ventana: sin datos", r.error !== undefined, true);

console.log("\nvalidado: con qué se contrastó cada registro (GDMTO y PDBT, 17 divisiones, 2025-09 a 2026-10)");
check("GDMTO Oriente 2026-09: DOF y recibo", (await v("tarifa=GDMTO&region=ORIENTE&anio=2026&mes=9")).validado, ["dof", "recibo"]);
check("PDBT Noroeste 2026-03: DOF y recibo", (await v("tarifa=PDBT&region=NOROESTE&anio=2026&mes=3")).validado, ["dof", "recibo"]);
check("PDBT Noroeste 2026-05 y 2025-09: también con recibo (Tepeyac, ±$1 con el fijo descontado)",
  [(await v("tarifa=PDBT&region=NOROESTE&anio=2026&mes=5")).validado, (await v("tarifa=PDBT&region=NOROESTE&anio=2025&mes=9")).validado],
  [["dof", "recibo"], ["dof", "recibo"]]);
check("PDBT Noroeste 2026-06: sin recibo (sus recibos no traen kWh facturados)", (await v("tarifa=PDBT&region=NOROESTE&anio=2026&mes=6")).validado, ["dof"]);
r = await v("tarifa=GDMTO&region=SURESTE&anio=2026&mes=9");
check("GDMTO Sureste 2026-09: precio oficial del DOF, sin recibo", r.validado, ["dof"]);
check("GDMTO Sureste: energía del portal y a 4 decimales (la captura que antes salía de otro mes)",
  [r.cargos.energia, r.energia_4dec, r.periodo_cfe], [1.238, 1.2376, "SEP-26"]);
r = await v("tarifa=PDBT&region=SURESTE&anio=2026&mes=9");
check("PDBT Sureste 2026-09: DOF y energía a 4 decimales", [r.validado, r.energia_precision, typeof r.energia_4dec], [["dof"], "dof_4_decimales", "number"]);
check("GDMTO Noroeste: DOF, sin recibo declarado", (await v("tarifa=GDMTO&region=NOROESTE&anio=2026&mes=9")).validado, ["dof"]);
check("GDMTO Oriente 2025-08 (antes de la ventana, con su aviso): también con DOF", (await v("tarifa=GDMTO&region=ORIENTE&anio=2025&mes=8")).validado, ["dof"]);
check("GDMTO Oriente 2025-05 (aviso no encontrado): sin validar", (await v("tarifa=GDMTO&region=ORIENTE&anio=2025&mes=5")).validado, []);
check("Oriente 2026-11 (aún sin aviso): sin validar", (await v("tarifa=GDMTO&region=ORIENTE&anio=2026&mes=11")).validado, []);
check("GDMTH no lleva validado", "validado" in (await v("tarifa=GDMTH&region=ORIENTE&anio=2026&mes=9")), false);
check("DAC no lleva validado", "validado" in (await v("tarifa=DAC&region=NOROESTE&anio=2026&mes=9")), false);
r = await v("tarifa=GDMTO&estado=SONORA&municipio=NAVOJOA&anio=2026&mes=9");
check("por municipio también", r.validado, ["dof"]);

console.log("\nvalidado en 1E: recibos de Navojoa, por mes y temporada");
r = await v("tarifa=1E&anio=2026&mes=8&temporada=verano");
check("1E 2026-08 verano: recibo, basico e intermedio_bajo (0.848 y 1.048)",
  [r.validado, r.bloques_validados, r.cargos.basico, r.cargos.intermedio_bajo], [["recibo"], ["basico", "intermedio_bajo"], 0.848, 1.048]);
r = await v("tarifa=1E&anio=2026&mes=9&temporada=verano");
check("1E 2026-09 verano: basico 0.851 e intermedio_bajo 1.051",
  [r.validado, r.bloques_validados, r.cargos.basico, r.cargos.intermedio_bajo], [["recibo"], ["basico", "intermedio_bajo"], 0.851, 1.051]);
r = await v("tarifa=1E&anio=2026&mes=7&temporada=verano");
check("1E 2026-07 verano: los cuatro bloques con un recibo de 2,113 kWh (0.845, 1.045, 1.356 y 4.016)",
  [r.validado, r.bloques_validados, r.cargos.basico, r.cargos.intermedio_bajo, r.cargos.intermedio_alto, r.cargos.excedente],
  [["recibo"], ["basico", "intermedio_bajo", "intermedio_alto", "excedente"], 0.845, 1.045, 1.356, 4.016]);
r = await v("tarifa=1E&anio=2026&mes=6&temporada=verano");
check("1E 2026-06 verano: solo basico (sin recibo de los otros bloques)", r.bloques_validados, ["basico"]);
r = await v("tarifa=1E&anio=2026&mes=4&temporada=fuera_verano");
check("1E 2026-04 fuera de verano: solo basico (1.119)", [r.validado, r.bloques_validados, r.cargos.basico], [["recibo"], ["basico"], 1.119]);
r = await v("tarifa=1E&anio=2025&mes=11&temporada=fuera_verano");
check("1E 2025-11 fuera de verano: basico 1.103", [r.validado, r.cargos.basico], [["recibo"], 1.103]);
r = await v("tarifa=1E&anio=2025&mes=10&temporada=verano");
check("1E 2025-10 verano: basico 0.818", [r.validado, r.cargos.basico], [["recibo"], 0.818]);
r = await v("tarifa=1E&anio=2026&mes=8&temporada=fuera_verano");
check("1E 2026-08 pero fuera_verano: esa temporada no se validó con recibo", [r.validado, r.bloques_validados], [[], []]);
r = await v("tarifa=1E&anio=2026&mes=8&inicio_verano=5");
check("1E por inicio_verano=5 en 2026-08 cae en verano: validado", r.validado, ["recibo"]);
r = await v("tarifa=1E&anio=2025&mes=8&temporada=verano");
check("1E fuera del rango de recibos (2025-08): sin validar", r.validado, []);
r = await v("tarifa=1E&anio=2026&mes=11&temporada=fuera_verano");
check("1E 2026-11: sin validar", r.validado, []);
check("1E: la nota ya no dice que no esta validada", r.nota.includes("Precios sin validar"), false);
r = await v("tarifa=1F&anio=2023&mes=3&temporada=fuera_verano");
check("1F 2023-03 fuera de verano: recibo bimestral con los tres bloques (0.957, 1.167, 3.409)",
  [r.validado, r.bloques_validados, r.cargos.basico, r.cargos.intermedio, r.cargos.excedente],
  [["recibo"], ["basico", "intermedio", "excedente"], 0.957, 1.167, 3.409]);
r = await v("tarifa=1F&anio=2023&mes=5&temporada=verano");
check("1F 2023-05 verano: recibo con tres bloques (0.717, 0.898 y 2.184)",
  [r.validado, r.bloques_validados, r.cargos.basico, r.cargos.intermedio_bajo, r.cargos.intermedio_alto],
  [["recibo"], ["basico", "intermedio_bajo", "intermedio_alto"], 0.717, 0.898, 2.184]);
check("1F 2023-05 verano: el excedente no está validado", r.bloques_validados.includes("excedente"), false);
r = await v("tarifa=1F&anio=2023&mes=6&temporada=verano");
check("1F 2023-06 (clave distinta del recibo): sin validar", r.validado, []);
r = await v("tarifa=1F&anio=2023&mes=3&temporada=verano");
check("1F 2023-03 pero verano: esa temporada no se validó", [r.validado, r.bloques_validados], [[], []]);
r = await v("tarifa=1F&anio=2023&mes=2&temporada=fuera_verano");
check("1F 2023-02 (clave distinta del recibo): sin validar", r.validado, []);
r = await v("tarifa=1F&anio=2025&mes=3&temporada=fuera_verano");
check("1F 2025-03: sin validar (el recibo es de 2023)", r.validado, []);
for (const c of ["1", "1A", "1B", "1C", "1D"]) {
  const x = await v(`tarifa=${c}&anio=2026&mes=8&temporada=verano`);
  check(`${c} no lleva validado ni bloques_validados`, ["validado" in x, "bloques_validados" in x], [false, false]);
}
check("la nota de /v1/tarifas de 1E menciona bloques_validados", JSON.stringify((await get("/v1/tarifas")).cuerpo.tarifas.find((x) => x.tarifa === "1E")).includes("bloques_validados"), true);
let todos = 0, sin = [];
for (const reg of ["BAJA CALIFORNIA","BAJA CALIFORNIA SUR","BAJIO","CENTRO OCCIDENTE","CENTRO ORIENTE","CENTRO SUR","GOLFO CENTRO","GOLFO NORTE","JALISCO","NOROESTE","NORTE","ORIENTE","PENINSULAR","SURESTE","VALLE DE MEXICO CENTRO","VALLE DE MEXICO NORTE","VALLE DE MEXICO SUR"]) {
  for (const t of ["GDMTO", "PDBT"]) {
    for (const [a, m] of [[2025, 9], [2026, 3], [2026, 10]]) {
      const x = await v(`tarifa=${t}&region=${encodeURIComponent(reg)}&anio=${a}&mes=${m}`);
      todos++;
      if (!x.validado?.includes("dof")) sin.push(`${t} ${reg} ${a}-${m}`);
    }
  }
}
check(`las 17 divisiones, ${todos} consultas de muestra: todas con DOF`, sin, []);

console.log();
if (contar()) {
  console.log(`${contar()} prueba(s) fallaron.`);
  process.exit(1);
}
console.log("Todas las pruebas pasaron.");
