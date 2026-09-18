/**
 * Bootstrap compartido para las pruebas del Worker.
 *
 * Empaqueta src/ con esbuild sobre una COPIA de data/ (nunca el real) e
 * inyecta un par de casos de ejemplo que la semilla no trae: un municipio
 * con dos divisiones (BAJIO Y GOLFO CENTRO) y otro con dos opciones ya
 * separadas en el desplegable (CELAYA). Lo usan tanto prueba_api.mjs como
 * prueba_mcp.mjs, para no mantener dos copias de la misma configuración.
 */
import { build } from "esbuild";
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
// En Windows, import() exige una URL file://; una ruta absoluta "C:\..." falla.
import { pathToFileURL } from "node:url";

export const BASE = "https://ejemplo.workers.dev";

export async function crearWorker() {
  const dir = mkdtempSync(path.join(tmpdir(), "worker-"));

  cpSync("src", path.join(dir, "worker", "src"), { recursive: true });
  cpSync("../data", path.join(dir, "data"), { recursive: true });

  const rutaDatos = (n) => path.join(dir, "data", n);
  const leer = (n) => JSON.parse(readFileSync(rutaDatos(n), "utf8"));
  const escribir = (n, d) => writeFileSync(rutaDatos(n), JSON.stringify(d, null, 1));

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
  return worker;
}

/** Pequeño verificador con contador de fallos, compartido por ambos archivos. */
export function crearVerificador() {
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
  return { check, contar: () => fallos };
}
