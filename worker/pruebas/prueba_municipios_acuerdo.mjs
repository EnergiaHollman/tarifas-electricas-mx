/**
 * Pruebas del complemento de municipios (data/municipios_complemento.json).
 *
 *   cd worker && node pruebas/prueba_municipios_acuerdo.mjs
 *
 * Contexto: el catálogo sale del desplegable del portal de CFE, que está atrasado
 * frente al numeral 5.9 del Acuerdo CNE: le faltan municipios de creación reciente
 * (San Felipe, San Quintín, Seybaplaya...) y trunca o abrevia nombres ("DR.
 * ARROYO", "COAHUAYUTLA DE JOSE MARIA IZAZ"). El complemento -alias y ausentes- se
 * consulta SOLO cuando el catálogo no encuentra el municipio.
 *
 * La primera parte es una guarda de integridad sobre los datos reales; la segunda
 * demuestra que realmente falla cuando debe (datos mutados).
 */
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { BASE, crearVerificador, crearWorker } from "./_entorno.mjs";

const { check, contar } = crearVerificador();
const leer = (dir, n) => JSON.parse(readFileSync(path.join(dir, n), "utf8"));

// Mismo criterio que normalizar() de worker/src/datos.ts.
const normalizar = (t) => (t ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, " ").trim().toUpperCase();

/**
 * Problemas del complemento en un directorio de datos, separados en:
 *  - errores: algo se ROMPE (clave inexistente, división sin horario o sin tarifas...). Fallan el CI.
 *  - avisos: datos obsoletos pero inofensivos (el portal corrigió un nombre y el alias ya no se usa).
 *    Solo se informan: fallar por esto bloquearía el despliegue mensual desatendido sin motivo.
 */
function problemasDelComplemento(dir) {
  const comp = leer(dir, "municipios_complemento.json");
  const cat = leer(dir, "catalogo.json");
  const horario = leer(dir, "sistemas_horario.json").divisiones;
  const conTarifa = new Set(Object.values(leer(dir, "tarifas.json").registros).map((r) => r.region));
  const problemas = [];      // errores
  const avisos = [];
  const vistos = new Set();

  for (const [estado, lista] of Object.entries(comp.alias ?? {})) {
    const e = cat.estados[estado];
    if (!e) { problemas.push(`alias: el estado ${estado} no está en el catálogo`); continue; }
    for (const a of lista) {
      if (!(a.catalogo in e.municipios))
        problemas.push(`alias ${estado}: '${a.oficial}' apunta a una clave que no existe en el catálogo: '${a.catalogo}'`);
      if (normalizar(a.oficial) in e.municipios)
        avisos.push(`alias ${estado}: '${a.oficial}' ya está en el catálogo con ese nombre (el alias no se usa; se puede quitar)`);
      const k = `${estado}|${normalizar(a.oficial)}`;
      if (vistos.has(k)) problemas.push(`duplicado en el complemento: ${k}`);
      vistos.add(k);
    }
  }
  for (const [estado, lista] of Object.entries(comp.ausentes ?? {})) {
    const e = cat.estados[estado];
    if (!e) { problemas.push(`ausentes: el estado ${estado} no está en el catálogo`); continue; }
    for (const a of lista) {
      if (normalizar(a.oficial) in e.municipios)
        avisos.push(`ausente ${estado}: '${a.oficial}' ya está en el catálogo (no está ausente; se puede quitar)`);
      if (!a.divisiones?.length) problemas.push(`ausente ${estado}: '${a.oficial}' no trae ninguna división`);
      for (const d of a.divisiones ?? []) {
        if (!(d in horario)) problemas.push(`ausente ${estado}: '${a.oficial}' -> división sin sistema de horario: ${d}`);
        if (!conTarifa.has(d)) problemas.push(`ausente ${estado}: '${a.oficial}' -> división sin tarifas capturadas: ${d}`);
      }
      const k = `${estado}|${normalizar(a.oficial)}`;
      if (vistos.has(k)) problemas.push(`duplicado en el complemento: ${k}`);
      vistos.add(k);
    }
  }
  // Divergencias portal/Acuerdo: lo que se advierte al usuario no puede estar roto ni desactualizado.
  const divisionesDe = (e, clave) => new Set((cat.estados[e].municipios[clave].opciones ?? [])
    .flatMap((o) => cat.expansiones?.[normalizar(o.etiqueta)] ?? [normalizar(o.etiqueta)]));
  for (const [estado, lista] of Object.entries(comp.divergencias ?? {})) {
    const e = cat.estados[estado];
    if (!e) { problemas.push(`divergencias: el estado ${estado} no está en el catálogo`); continue; }
    for (const d of lista) {
      if (!(d.catalogo in e.municipios)) {
        problemas.push(`divergencia ${estado}: '${d.catalogo}' no existe en el catálogo`);
        continue;
      }
      for (const div of d.acuerdo) {
        if (!conTarifa.has(div)) problemas.push(`divergencia ${estado}: '${d.catalogo}' -> el Acuerdo manda a una división sin tarifas capturadas: ${div}`);
      }
      const portal = [...divisionesDe(estado, d.catalogo)].sort();
      if (JSON.stringify(portal) === JSON.stringify([...d.acuerdo].sort()))
        avisos.push(`divergencia ${estado}: '${d.catalogo}' ya coincide con el Acuerdo (el portal cambió; se puede quitar)`);
      else if (JSON.stringify(portal) !== JSON.stringify([...d.portal].sort()))
        avisos.push(`divergencia ${estado}: '${d.catalogo}' ya no dice lo mismo en el portal (${portal.join("+")}); regenerar con cruzar_catalogo.py`);
    }
  }
  return { errores: problemas, avisos };
}

console.log("1. Guarda de integridad sobre los datos reales (../data)");
const reales = problemasDelComplemento("../data");
check("el complemento es consistente con el catálogo, los horarios y las tarifas", reales.errores, []);
if (reales.errores.length) console.log("   " + reales.errores.join("\n   "));
for (const a of reales.avisos) console.log("   aviso (no falla):", a);
const comp = leer("../data", "municipios_complemento.json");
const nAlias = Object.values(comp.alias).flat().length;
const nAus = Object.values(comp.ausentes).flat().length;
check("hay alias y ausentes (el archivo no está vacío)", nAlias > 0 && nAus > 0, true);
check("hay divergencias registradas", Object.values(comp.divergencias).flat().length > 0, true);

console.log("\n2. La guarda realmente FALLA cuando debe (datos mutados)");
function copiaMutada(mutar) {
  const dir = mkdtempSync(path.join(tmpdir(), "municipios-"));
  cpSync("../data", dir, { recursive: true });
  const c = leer(dir, "municipios_complemento.json");
  mutar(c);
  writeFileSync(path.join(dir, "municipios_complemento.json"), JSON.stringify(c));
  return dir;
}
check("un alias que apunta a una clave inexistente del catálogo se detecta",
  problemasDelComplemento(copiaMutada((c) => { c.alias["NUEVO LEON"][0].catalogo = "NO EXISTE"; }))
    .errores.some((p) => p.includes("clave que no existe")), true);
const obsoleto = problemasDelComplemento(copiaMutada((c) => { c.alias["NUEVO LEON"][0].oficial = "Monterrey"; }));
check("un alias que ya está en el catálogo se AVISA (obsoleto, inofensivo)", obsoleto.avisos.some((p) => p.includes("ya está en el catálogo")), true);
check("...pero NO es un error: no debe bloquear el despliegue", obsoleto.errores, []);
check("un 'ausente' con una división sin sistema de horario se detecta",
  problemasDelComplemento(copiaMutada((c) => { c.ausentes["SONORA"][0].divisiones = ["DIVISION NUEVA"]; }))
    .errores.some((p) => p.includes("sin sistema de horario")), true);
check("un 'ausente' que ya está en el catálogo se AVISA, sin fallar",
  (({ errores, avisos }) => [errores.length, avisos.some((p) => p.includes("no está ausente"))])(
    problemasDelComplemento(copiaMutada((c) => { c.ausentes["SONORA"][0].oficial = "Navojoa"; }))), [0, true]);
check("una divergencia hacia una división sin tarifas se detecta",
  problemasDelComplemento(copiaMutada((c) => { c.divergencias["ESTADO DE MEXICO"][0].acuerdo = ["DIVISION NUEVA"]; }))
    .errores.some((p) => p.includes("sin tarifas capturadas")), true);
check("una divergencia que apunta a un municipio inexistente se detecta",
  problemasDelComplemento(copiaMutada((c) => { c.divergencias["ESTADO DE MEXICO"][0].catalogo = "NO EXISTE"; }))
    .errores.some((p) => p.includes("no existe en el catálogo")), true);
const resuelta = problemasDelComplemento(copiaMutada((c) => {
  const d = c.divergencias["ESTADO DE MEXICO"].find((x) => x.catalogo === "TEXCOCO");
  d.acuerdo = [...d.portal];                       // el Acuerdo "coincide" con el portal
}));
check("una divergencia que el portal ya corrigió se AVISA, sin fallar",
  [resuelta.errores.length, resuelta.avisos.some((p) => p.includes("ya coincide con el Acuerdo"))], [0, true]);
check("un estado desconocido en el complemento se detecta",
  problemasDelComplemento(copiaMutada((c) => { c.ausentes["ATLANTIDA"] = [{ oficial: "X", divisiones: ["NOROESTE"] }]; }))
    .errores.some((p) => p.includes("no está en el catálogo")), true);

console.log("\n3. Comportamiento del Worker");
const worker = await crearWorker();
const get = async (ruta) => {
  const r = await worker.fetch(new Request(BASE + ruta));
  return { status: r.status, cuerpo: await r.json() };
};
const tarifa = (estado, mun) =>
  get(`/v1/tarifa?estado=${encodeURIComponent(estado)}&municipio=${encodeURIComponent(mun)}&anio=2026&mes=3`);

// Ausentes: el portal no los trae; la división sale del Acuerdo.
let r = await tarifa("SONORA", "General Plutarco Elías Calles");
check("ausente (Sonora, división BC): resuelve", r.status, 200);
check("ausente: va a la división BAJA CALIFORNIA", r.cuerpo.region, "BAJA CALIFORNIA");
check("ausente: el sistema de horario es BC", r.cuerpo.sistema_horario, "BC");
check("ausente: advierte que el municipio no vino del portal", typeof r.cuerpo.nota_municipio, "string");
const bc = await get("/v1/tarifa?region=BAJA CALIFORNIA&anio=2026&mes=3");
check("ausente: los cargos son EXACTAMENTE los de la división (no se inventa nada)",
  r.cuerpo.cargos, bc.cuerpo.cargos);

for (const [est, mun, division] of [
  ["BAJA CALIFORNIA", "San Felipe", "BAJA CALIFORNIA"],
  ["BAJA CALIFORNIA", "San Quintín", "BAJA CALIFORNIA"],
  ["CAMPECHE", "Seybaplaya", "PENINSULAR"],
  ["CAMPECHE", "Dzitbalché", "PENINSULAR"],
  ["SINALOA", "El Dorado", "NOROESTE"],
  ["VERACRUZ", "Paso de Ovejas", "ORIENTE"],
]) {
  r = await tarifa(est, mun);
  check(`ausente ${mun} (${est}): ${division}`, [r.status, r.cuerpo.region], [200, division]);
}

// Alias: el portal lo trae con otro nombre. (Se usan alias de etiqueta simple: el arnés de
// pruebas sobrescribe la tabla de expansiones, y las compuestas como la de "DR. ARROYO",
// 'GOLFO CENTRO Y GOLFO NORTE', quedarían sin expandir aquí; con los datos reales sí resuelve.)
r = await tarifa("NUEVO LEON", "Doctor Coss");
check("alias: 'Doctor Coss' resuelve aunque el portal diga 'DR. COSS'", [r.status, r.cuerpo.region], [200, "GOLFO NORTE"]);
const viejo = await tarifa("NUEVO LEON", "DR. COSS");
check("alias: da exactamente lo mismo que el nombre del portal", r.cuerpo.cargos, viejo.cuerpo.cargos);
check("alias: no lleva la nota (el municipio sí está en el portal)", r.cuerpo.nota_municipio, undefined);
r = await tarifa("NUEVO LEON", "General Bravo");
check("alias: 'General Bravo' (el portal dice 'GRAL. BRAVO')", [r.status, r.cuerpo.region], [200, "GOLFO NORTE"]);
r = await tarifa("GUERRERO", "Coahuayutla de José María Izazaga");
check("alias: el nombre oficial completo resuelve (el portal lo trunca a 30 caracteres)", r.status, 200);
r = await tarifa("MORELOS", "Zacualpan de Amilpas");
check("alias: Zacualpan de Amilpas (Morelos) no se confunde con otros Zacualpan", [r.status, r.cuerpo.region], [200, "CENTRO SUR"]);

// Regresión: lo que ya funcionaba no cambia.
r = await tarifa("SONORA", "NAVOJOA");
check("regresión: SONORA + NAVOJOA sigue resolviendo a NOROESTE", [r.status, r.cuerpo.region], [200, "NOROESTE"]);
check("regresión: sin nota para un municipio del portal", r.cuerpo.nota_municipio, undefined);
check("regresión: cargos de marzo 2026 intactos", r.cuerpo.cargos.base, 0.9715);
r = await tarifa("VERACRUZ", "BOCA DEL RIO");
check("regresión: VERACRUZ + BOCA DEL RIO sigue en ORIENTE", [r.status, r.cuerpo.region], [200, "ORIENTE"]);

// Divergencias: el portal manda; el Acuerdo se advierte, nunca reemplaza.
r = await tarifa("ESTADO DE MEXICO", "Texcoco");
check("divergencia (el portal da UNA división, el Acuerdo dos): la respuesta sigue al portal",
  [r.status, r.cuerpo.region], [200, "VALLE DE MEXICO CENTRO"]);
check("...y advierte lo que dice el Acuerdo", r.cuerpo.divisiones_segun_acuerdo, ["VALLE DE MEXICO CENTRO", "VALLE DE MEXICO NORTE"]);
check("...con una nota que dice cómo consultar la otra", /region/.test(r.cuerpo.nota_division ?? ""), true);
const otra = await get("/v1/tarifa?region=VALLE DE MEXICO NORTE&anio=2026&mes=3");
check("la otra división del Acuerdo se puede consultar con region", [otra.status, otra.cuerpo.region], [200, "VALLE DE MEXICO NORTE"]);

r = await tarifa("ESTADO DE MEXICO", "Toluca");
check("divergencia en un municipio con DOS divisiones en el portal (rama con 'resultados')",
  [r.status, r.cuerpo.resultados?.length, r.cuerpo.divisiones_segun_acuerdo], [200, 2, ["VALLE DE MEXICO SUR"]]);
check("...conserva estado y municipio en esa rama", [r.cuerpo.estado, r.cuerpo.municipio], ["ESTADO DE MÉXICO", "TOLUCA"]);
r = await tarifa("TABASCO", "Cárdenas");
check("divergencia: Cárdenas (portal SURESTE, Acuerdo ORIENTE y SURESTE)",
  [r.cuerpo.region, r.cuerpo.divisiones_segun_acuerdo], ["SURESTE", ["ORIENTE", "SURESTE"]]);

// Las dos copias del mismo municipio que el portal repite (nombre completo y truncado).
r = await tarifa("OAXACA", "Heroica Ciudad de Huajuapan de León");
check("copia con el nombre completo: portal SURESTE, Acuerdo CENTRO ORIENTE y SURESTE",
  [r.cuerpo.region, r.cuerpo.divisiones_segun_acuerdo], ["SURESTE", ["CENTRO ORIENTE", "SURESTE"]]);
r = await tarifa("OAXACA", "HEROICA CIUDAD DE HUAJUAPAN DE");
check("copia truncada: portal CENTRO ORIENTE, el Acuerdo dice lo mismo que arriba",
  [r.cuerpo.region, r.cuerpo.divisiones_segun_acuerdo], ["CENTRO ORIENTE", ["CENTRO ORIENTE", "SURESTE"]]);

// Sin divergencia no aparece nada (lo que ya funcionaba no cambia).
for (const [est, mun] of [["SONORA", "NAVOJOA"], ["VERACRUZ", "BOCA DEL RIO"], ["BAJA CALIFORNIA", "San Quintín"]]) {
  r = await tarifa(est, mun);
  check(`sin divergencia, sin campos nuevos: ${mun}`, [r.cuerpo.divisiones_segun_acuerdo, r.cuerpo.nota_division], [undefined, undefined]);
}

// La rama con VARIOS resultados también advierte los municipios del Acuerdo (defecto corregido:
// esa rama armaba estado/municipio a mano y se saltaba la nota). Hoy ningún ausente real tiene dos
// divisiones, así que se prueba con un dato fabricado.
const conDoble = await crearWorker({
  preparar: (dirDatos) => {
    const c = leer(dirDatos, "municipios_complemento.json");
    c.ausentes["SONORA"].push({ oficial: "Municipio De Prueba", divisiones: ["NOROESTE", "NORTE"] });
    writeFileSync(path.join(dirDatos, "municipios_complemento.json"), JSON.stringify(c));
  },
});
const rd = await (await conDoble.fetch(new Request(BASE + "/v1/tarifa?estado=SONORA&municipio=Municipio De Prueba&anio=2026&mes=3"))).json();
check("un ausente con DOS divisiones devuelve las dos", rd.resultados?.map((x) => x.region), ["NOROESTE", "NORTE"]);
check("...y conserva la nota de que no vino del portal", typeof rd.nota_municipio, "string");

// Lo desconocido sigue fallando.
r = await tarifa("SONORA", "Municipio Inventado");
check("un municipio que no existe sigue dando 404", r.status, 404);

// Horarios y calendario por la misma vía.
r = await get("/v1/calendario?estado=SONORA&municipio=General Plutarco Elías Calles&anio=2026");
check("calendario de un ausente: resuelve con el sistema BC", [r.status, r.cuerpo.sistema_horario], [200, "BC"]);
check("calendario de un ausente: el verano de BC empieza el 1 de mayo", r.cuerpo.verano.inicio, "2026-05-01");
r = await get("/v1/horarios?estado=CAMPECHE&municipio=Seybaplaya&fecha=2026-08-14&hora=20:30");
check("horarios de un ausente: resuelve (SIN) y marca punta", [r.status, r.cuerpo.sistema_horario, r.cuerpo.consulta.periodo], [200, "SIN", "punta"]);

// Listado.
r = await get("/v1/municipios?estado=BAJA CALIFORNIA");
const nombres = r.cuerpo.municipios.map((m) => m.nombre);
check("el listado incluye San Felipe y San Quintín", ["SAN FELIPE", "SAN QUINTIN"].every((n) => nombres.includes(n)), true);
check("los del Acuerdo se marcan con origen", r.cuerpo.municipios.filter((m) => m.origen === "acuerdo").length, 2);
check("BC tiene ahora los 7 municipios oficiales", nombres.length, 7);
r = await get("/v1/municipios?estado=SONORA");
check("Sonora: el listado incluye Plutarco Elías Calles y Ures",
  ["GENERAL PLUTARCO ELIAS CALLES", "URES"].every((n) => r.cuerpo.municipios.some((m) => m.nombre === n)), true);

console.log();
if (contar()) {
  console.log(`${contar()} prueba(s) fallaron.`);
  process.exit(1);
}
console.log("Todas las pruebas pasaron.");
