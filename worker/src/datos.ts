/**
 * Acceso a los datos capturados. Los tres JSON se empaquetan dentro del
 * Worker al hacer deploy, así que estas consultas son lecturas en memoria:
 * sin base de datos, sin red, sin latencia.
 */
import catalogoJson from "../../data/catalogo.json";
import horariosJson from "../../data/horarios.json";
import tarifasJson from "../../data/tarifas.json";
import type { Zona } from "./calendario";

type Municipio = { id: string; nombre: string; region: string; region_id: string };
type Estado = { id: string; nombre: string; municipios: Record<string, Municipio> };

export const catalogo = catalogoJson as unknown as {
  generado: string | null;
  fuente: string;
  parcial?: boolean;
  estados: Record<string, Estado>;
};

export const horarios = horariosJson as unknown as {
  generado: string | null;
  fuente: string;
  zonas: Record<string, Zona>;
};

export type Registro = {
  tarifa: string;
  region: string;
  anio: number;
  mes: number;
  periodo_cfe: string;
  cargos: Record<string, number>;
  unidades: Record<string, string>;
  conceptos: { int_horario: string; cargo: string; unidades: string; valor: number }[];
  municipio_consultado?: string;
  fuente: string;
  fecha_captura: string;
};

export const tarifas = tarifasJson as unknown as {
  actualizado: string | null;
  fuente: string;
  registros: Record<string, Registro>;
};

/** Mayúsculas sin acentos. Mismo criterio que el scraper en Python. */
export function normalizar(t: string): string {
  return (t ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toUpperCase();
}

export function listarEstados(): string[] {
  return Object.values(catalogo.estados).map((e) => e.nombre).sort();
}

export function listarMunicipios(estado: string): Municipio[] | null {
  const e = catalogo.estados[normalizar(estado)];
  if (!e) return null;
  return Object.values(e.municipios).sort((a, b) => a.nombre.localeCompare(b.nombre));
}

export function regionDeMunicipio(estado: string, municipio: string): Municipio | null {
  const e = catalogo.estados[normalizar(estado)];
  if (!e) return null;
  return e.municipios[normalizar(municipio)] ?? null;
}

export function listarRegiones(): string[] {
  const s = new Set<string>();
  for (const r of Object.values(tarifas.registros)) s.add(r.region);
  for (const e of Object.values(catalogo.estados))
    for (const m of Object.values(e.municipios)) s.add(m.region);
  return [...s].sort();
}

export function obtenerTarifa(
  tarifa: string,
  region: string,
  anio: number,
  mes: number,
): Registro | null {
  const k = `${normalizar(tarifa)}|${normalizar(region)}|${anio}-${String(mes).padStart(2, "0")}`;
  return tarifas.registros[k] ?? null;
}

/** Periodos disponibles de una región, para decir qué sí hay cuando falta uno. */
export function periodosDe(tarifa: string, region: string): string[] {
  const pre = `${normalizar(tarifa)}|${normalizar(region)}|`;
  return Object.keys(tarifas.registros)
    .filter((k) => k.startsWith(pre))
    .map((k) => k.slice(pre.length))
    .sort();
}

export function zonaDeRegion(region: string): Zona | null {
  const r = normalizar(region);
  for (const z of Object.values(horarios.zonas)) {
    if (z.regiones.map(normalizar).includes(r)) return z;
  }
  return null;
}

export const AVISO =
  "Datos capturados automáticamente del portal público de CFE. Este no es un " +
  "servicio oficial de CFE ni está afiliado a ella. La fuente autoritativa es " +
  "el portal de CFE; verifica ahí antes de usar estas cifras para facturación " +
  "o decisiones de inversión.";
