/**
 * Pruebas del mapa división tarifaria -> sistema interconectado de horario.
 *
 *   cd worker && node pruebas/prueba_sistemas_horario.mjs
 *
 * Contexto: los cargos dependen de la división (17) y los horarios del sistema
 * interconectado (SIN, BC, BCS). Antes, 12 de las 17 divisiones respondían
 * "Región desconocida" en /v1/calendario porque solo coincidían por casualidad
 * las que compartían nombre con la etiqueta heredada del portal. Regla oficial:
 * Acuerdo CNE CT/11.SE/8-2025, numeral 3.1.5 c.
 *
 * La primera parte es una GUARDA DE INTEGRIDAD sobre los datos reales
 * (../data): si el scraper captura una división nueva y nadie la agrega a
 * data/sistemas_horario.json, esto falla -en CI, antes de desplegar- en vez de
 * dejar que esa división herede en silencio un horario que nadie verificó.
 */
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { BASE, crearVerificador, crearWorker } from "./_entorno.mjs";

const { check, contar } = crearVerificador();
const leer = (dir, n) => JSON.parse(readFileSync(path.join(dir, n), "utf8"));

/** Devuelve la lista de problemas de integridad de un directorio de datos. */
function problemasDeIntegridad(dir) {
  const problemas = [];
  const mapa = leer(dir, "sistemas_horario.json");
  const tarifas = leer(dir, "tarifas.json").registros;
  const catalogo = leer(dir, "catalogo.json");

  const conTarifa = new Set(Object.values(tarifas).map((r) => r.region));
  const enMapa = new Set(Object.keys(mapa.divisiones));

  for (const d of [...conTarifa].sort())
    if (!enMapa.has(d)) problemas.push(`división con tarifas y SIN sistema de horario: ${d}`);
  for (const d of [...enMapa].sort())
    if (!conTarifa.has(d)) problemas.push(`división en el mapa sin ninguna tarifa capturada: ${d}`);

  // Toda división alcanzable desde el catálogo de municipios también debe estar mapeada.
  const exp = catalogo.expansiones ?? {};
  for (const e of Object.values(catalogo.estados))
    for (const m of Object.values(e.municipios))
      for (const o of m.opciones ?? [])
        for (const d of exp[o.etiqueta] ?? [o.etiqueta])
          if (!enMapa.has(d)) problemas.push(`el catálogo (${m.nombre}) apunta a una división sin sistema: ${d}`);

  for (const [d, s] of Object.entries(mapa.divisiones))
    if (!(s in mapa.sistemas)) problemas.push(`${d} usa un sistema desconocido: ${s}`);

  // La regla oficial: BC y BCS a las divisiones del mismo nombre; SIN al resto.
  for (const [d, s] of Object.entries(mapa.divisiones)) {
    const esperado = d === "BAJA CALIFORNIA" ? "BC" : d === "BAJA CALIFORNIA SUR" ? "BCS" : "SIN";
    if (s !== esperado) problemas.push(`${d}: el Acuerdo 3.1.5 c manda ${esperado}, el mapa dice ${s}`);
  }
  return [...new Set(problemas)];
}

console.log("1. Guarda de integridad sobre los datos reales (../data)");
const reales = problemasDeIntegridad("../data");
check("sin problemas de integridad en los datos reales", reales, []);
if (reales.length) console.log("   " + reales.join("\n   "));

console.log("\n2. La guarda realmente FALLA cuando debe (se prueba con datos mutados)");
function copiaMutada(mutar) {
  const dir = mkdtempSync(path.join(tmpdir(), "integridad-"));
  cpSync("../data", dir, { recursive: true });
  mutar(dir);
  return dir;
}
const conDivisionNueva = copiaMutada((dir) => {
  const t = leer(dir, "tarifas.json");
  t.registros["GDMTH|DIVISION NUEVA|2026-01"] = { tarifa: "GDMTH", region: "DIVISION NUEVA", anio: 2026, mes: 1, cargos: {} };
  writeFileSync(path.join(dir, "tarifas.json"), JSON.stringify(t));
});
check("una división nueva en tarifas.json sin sistema se detecta",
  problemasDeIntegridad(conDivisionNueva).some((p) => p.includes("DIVISION NUEVA")), true);

const conMapaMalo = copiaMutada((dir) => {
  const m = leer(dir, "sistemas_horario.json");
  m.divisiones["ORIENTE"] = "BC";            // contradice la regla del Acuerdo
  writeFileSync(path.join(dir, "sistemas_horario.json"), JSON.stringify(m));
});
check("un mapa que contradice la regla oficial se detecta",
  problemasDeIntegridad(conMapaMalo).some((p) => p.startsWith("ORIENTE")), true);

const sinUnaDivision = copiaMutada((dir) => {
  const m = leer(dir, "sistemas_horario.json");
  delete m.divisiones["ORIENTE"];
  writeFileSync(path.join(dir, "sistemas_horario.json"), JSON.stringify(m));
});
check("quitar una división del mapa se detecta (el caso que ocurrió en producción)",
  problemasDeIntegridad(sinUnaDivision).some((p) => p.includes("ORIENTE")), true);

console.log("\n3. Comportamiento del Worker");
const worker = await crearWorker();
const get = async (ruta) => {
  const r = await worker.fetch(new Request(BASE + ruta));
  return { status: r.status, cuerpo: await r.json() };
};

const mapa = leer("../data", "sistemas_horario.json");
const divisiones = Object.keys(mapa.divisiones);
check("el mapa cubre las 17 divisiones tarifarias del Acuerdo", divisiones.length, 17);

let fallan = [];
for (const d of divisiones) {
  const r = await get(`/v1/calendario?region=${encodeURIComponent(d)}&anio=2026`);
  if (r.status !== 200) fallan.push(d);
}
check("las 17 divisiones resuelven en /v1/calendario (antes fallaban 12)", fallan, []);

let r = await get("/v1/calendario?estado=VERACRUZ&municipio=BOCA DEL RIO&anio=2026");
check("Boca del Río (estado + municipio) resuelve", r.status, 200);
check("Boca del Río: división ORIENTE", r.cuerpo.division, "ORIENTE");
check("Boca del Río: sistema de horario SIN", r.cuerpo.sistema_horario, "SIN");

// ORIENTE y NOROESTE son ambos SIN: deben traer EXACTAMENTE el mismo horario.
const oriente = (await get("/v1/calendario?region=ORIENTE&anio=2026")).cuerpo;
const noroeste = (await get("/v1/calendario?region=NOROESTE&anio=2026")).cuerpo;
check("ORIENTE y NOROESTE (mismo sistema) comparten franjas", oriente.dias, noroeste.dias);
check("ORIENTE y NOROESTE comparten temporadas", [oriente.verano, oriente.invierno], [noroeste.verano, noroeste.invierno]);

// Borde de temporada 2026 del SIN: el verano termina el sábado ANTERIOR al
// último domingo de octubre (24), no el último sábado de octubre (31).
check("SIN 2026: el verano empieza el 5 de abril (primer domingo)", oriente.verano.inicio, "2026-04-05");
check("SIN 2026: el verano termina el 24 de octubre, no el 31", oriente.verano.fin, "2026-10-24");

// Punta del SIN según el Acuerdo (Tabla 5): minutos desde medianoche.
check("SIN verano, lunes a viernes: punta 20:00-22:00", oriente.dias.verano.habil.punta, [[1200, 1320]]);
check("SIN invierno, lunes a viernes: punta 18:00-22:00", oriente.dias.invierno.habil.punta, [[1080, 1320]]);
check("SIN invierno, SÁBADO: punta 19:00-21:00 (fácil de olvidar al contar horas)",
  oriente.dias.invierno.sabado.punta, [[1140, 1260]]);
check("SIN verano, sábado: sin punta", oriente.dias.verano.sabado.punta, []);

// BC y BCS siguen con sus propios horarios, distintos del SIN.
const bc = (await get("/v1/calendario?region=BAJA CALIFORNIA&anio=2026")).cuerpo;
const bcs = (await get("/v1/calendario?region=BAJA CALIFORNIA SUR&anio=2026")).cuerpo;
check("BAJA CALIFORNIA: sistema BC", bc.sistema_horario, "BC");
check("BAJA CALIFORNIA SUR: sistema BCS", bcs.sistema_horario, "BCS");
check("BC: el verano empieza el 1 de mayo (calendario propio)", bc.verano.inicio, "2026-05-01");
check("BC y SIN no comparten franjas", JSON.stringify(bc.dias) === JSON.stringify(oriente.dias), false);
check("BCS y SIN no comparten franjas", JSON.stringify(bcs.dias) === JSON.stringify(oriente.dias), false);

console.log("\n4. Contrato de /v1/calendario?region=&anio= (lo usa el motor del Dashboard, D-028)");
const llavesContrato = ["region", "zona", "anio", "verano", "invierno", "festivos", "dias", "nota", "fuente", "aviso"];
check("siguen todas las llaves de siempre",
  llavesContrato.filter((k) => !(k in oriente)), []);
check("region sigue siendo el nombre pedido", oriente.region, "ORIENTE");
check("verano conserva inicio, fin y vigencia", Object.keys(oriente.verano).sort(), ["fin", "inicio", "vigencia"]);
check("dias conserva verano e invierno", Object.keys(oriente.dias).sort(), ["invierno", "verano"]);
check("cada temporada conserva habil, sabado y domingo", Object.keys(oriente.dias.verano).sort(), ["domingo", "habil", "sabado"]);

console.log("\n5. Nombres heredados del portal siguen funcionando (compatibilidad)");
for (const legado of ["CENTRAL", "NORESTE", "SUR"]) {
  r = await get(`/v1/calendario?region=${legado}&anio=2026`);
  check(`${legado} (nombre heredado) sigue resolviendo`, r.status, 200);
  check(`${legado}: no se presenta como división`, r.cuerpo.division, null);
  check(`${legado}: sistema SIN`, r.cuerpo.sistema_horario, "SIN");
}

console.log("\n6. division y sistema_horario aparecen, de forma aditiva, en todas las respuestas");
r = await get("/v1/tarifa?estado=VERACRUZ&municipio=BOCA DEL RIO&anio=2026&mes=8");
check("/v1/tarifa trae division", r.cuerpo.division, "ORIENTE");
check("/v1/tarifa trae sistema_horario", r.cuerpo.sistema_horario, "SIN");
check("/v1/tarifa conserva region y cargos", [r.cuerpo.region, r.cuerpo.cargos.distribucion, r.cuerpo.cargos.capacidad], ["ORIENTE", 202.45, 346.2]);

r = await get("/v1/horarios?region=ORIENTE&fecha=2026-08-15&hora=20:30");
check("/v1/horarios ORIENTE resuelve (antes: Región desconocida)", r.status, 200);
check("/v1/horarios trae sistema_horario", r.cuerpo.sistema_horario, "SIN");
check("20:30 de un sábado de verano en ORIENTE: intermedia (no hay punta en sábado)", r.cuerpo.consulta.periodo, "intermedia");

r = await get("/v1/horarios?region=ORIENTE&fecha=2026-01-15&hora=20:30");
check("20:30 de un jueves de invierno en ORIENTE: punta", r.cuerpo.consulta.periodo, "punta");

// Municipio con dos divisiones: cada resultado lleva su propio sistema.
r = await get("/v1/tarifa?estado=GUANAJUATO&municipio=SAN LUIS DE LA PAZ&anio=2026&mes=3");
check("varias divisiones: cada resultado trae sistema_horario",
  r.cuerpo.resultados.map((x) => x.sistema_horario), ["SIN", "SIN"]);

r = await get("/v1/regiones");
check("/v1/regiones: las 17 con zona (antes 5)", r.cuerpo.regiones.filter((x) => x.zona).length >= 17, true);
check("/v1/regiones trae sistema_horario por división",
  r.cuerpo.regiones.find((x) => x.region === "ORIENTE").sistema_horario, "SIN");

console.log("\n7. Una división desconocida FALLA; no hereda el horario del SIN en silencio");
r = await get("/v1/calendario?region=DIVISION INVENTADA&anio=2026");
check("región inventada: HTTP 404", r.status, 404);
check("región inventada: error explícito", String(r.cuerpo.error).includes("Región desconocida"), true);

const conNueva = await crearWorker({
  preparar: (dirDatos) => {
    const t = leer(dirDatos, "tarifas.json");
    t.registros["GDMTH|DIVISION NUEVA|2026-03"] = JSON.parse(JSON.stringify(t.registros["GDMTH|NOROESTE|2026-03"]));
    t.registros["GDMTH|DIVISION NUEVA|2026-03"].region = "DIVISION NUEVA";
    writeFileSync(path.join(dirDatos, "tarifas.json"), JSON.stringify(t));
  },
});
const rn = await conNueva.fetch(new Request(BASE + "/v1/calendario?region=DIVISION NUEVA&anio=2026"));
check("división nueva con tarifas pero sin sistema: el calendario falla (404)", rn.status, 404);
const rt = await (await conNueva.fetch(new Request(BASE + "/v1/tarifa?region=DIVISION NUEVA&anio=2026&mes=3"))).json();
check("pero sus cargos sí se sirven; el horario queda en null, no inventado", rt.sistema_horario, null);

console.log();
if (contar()) {
  console.log(`${contar()} prueba(s) fallaron.`);
  process.exit(1);
}
console.log("Todas las pruebas pasaron.");
