/**
 * Acceso a los datos capturados. Los tres JSON se empaquetan dentro del
 * Worker al hacer deploy, así que estas consultas son lecturas en memoria:
 * sin base de datos, sin red, sin latencia.
 */
import catalogoJson from "../../data/catalogo.json";
import horariosJson from "../../data/horarios.json";
import sistemasJson from "../../data/sistemas_horario.json";
import complementoJson from "../../data/municipios_complemento.json";
import tarifasJson from "../../data/tarifas.json";
import type { Zona } from "./calendario";

type Opcion = { id: string; etiqueta: string };
type Municipio = {
  id: string; nombre: string;
  opciones?: Opcion[];
  region?: string; region_id?: string;   // formato viejo del catálogo
  origen?: "acuerdo";                    // no viene del portal: se completó con el Acuerdo
  acuerdo?: string[];                    // el Acuerdo asigna OTRAS divisiones que el portal
};
type Estado = { id: string; nombre: string; municipios: Record<string, Municipio> };

export const catalogo = catalogoJson as unknown as {
  generado: string | null;
  fuente: string;
  parcial?: boolean;
  /** Etiqueta del desplegable -> divisiones reales, aprendidas al capturar. */
  expansiones?: Record<string, string[]>;
  estados: Record<string, Estado>;
};

export const horarios = horariosJson as unknown as {
  generado: string | null;
  fuente: string;
  zonas: Record<string, Zona>;
};

/**
 * División tarifaria -> sistema interconectado de horario.
 *
 * Los CARGOS dependen de la división (17); los HORARIOS dependen del sistema
 * interconectado (3: SIN, BC y BCS). Son conceptos distintos: la regla oficial
 * (Acuerdo CNE CT/11.SE/8-2025, numeral 3.1.5 c) asigna BC y BCS a las
 * divisiones del mismo nombre y el SIN al resto. Vive en un archivo curado
 * aparte (data/sistemas_horario.json) porque horarios.json lo regenera el
 * scraper en cada corrida y borraría cualquier edición manual.
 */
export type ClaveSistema = "SIN" | "BC" | "BCS";

export const sistemasHorario = sistemasJson as unknown as {
  fuente: string;
  regla_literal: string;
  vigencia_confirmada: string;
  sistemas: Record<string, { nombre: string; zona_contiene: string }>;
  divisiones: Record<string, string>;
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

/**
 * Respaldo del catálogo de municipios, generado del numeral 5.9 del Acuerdo CNE
 * (data/municipios_complemento.json, curado a mano; el scraper no lo toca).
 *
 * El catálogo sale del desplegable del portal de CFE y está atrasado frente al
 * Acuerdo: le faltan municipios de creación reciente (San Felipe, San Quintín,
 * Seybaplaya...) y usa nombres abreviados o truncados a 30 caracteres ("DR.
 * ARROYO", "COAHUAYUTLA DE JOSE MARIA IZAZ"). Se consulta SOLO cuando el
 * catálogo no encuentra el municipio, así que lo que ya resolvía no cambia.
 *   alias    -> nombre oficial del Acuerdo -> clave del municipio en el catálogo
 *   ausentes -> el portal no lo trae; la división sale del Acuerdo
 */
export const complemento = complementoJson as unknown as {
  fuente: string;
  alias: Record<string, { oficial: string; catalogo: string }[]>;
  ausentes: Record<string, { oficial: string; divisiones: string[] }[]>;
  divergencias: Record<string, { catalogo: string; oficial: string; portal: string[]; acuerdo: string[] }[]>;
};

const indiceAlias = new Map<string, string>();                                   // "ESTADO|NOMBRE" -> clave
const indiceAusentes = new Map<string, { oficial: string; divisiones: string[] }>();
for (const [estado, lista] of Object.entries(complemento.alias ?? {}))
  for (const a of lista) indiceAlias.set(`${estado}|${normalizar(a.oficial)}`, a.catalogo);
for (const [estado, lista] of Object.entries(complemento.ausentes ?? {}))
  for (const a of lista) indiceAusentes.set(`${estado}|${normalizar(a.oficial)}`, a);

// Municipios que el portal y el Acuerdo asignan a divisiones distintas. No se corrige ninguno
// de los dos: la respuesta sigue al portal y advierte lo que dice el Acuerdo.
const indiceDivergencias = new Map<string, string[]>();                          // "ESTADO|CLAVE" -> divisiones del Acuerdo
for (const [estado, lista] of Object.entries(complemento.divergencias ?? {}))
  for (const d of lista) indiceDivergencias.set(`${estado}|${d.catalogo}`, d.acuerdo);

/** El municipio del catálogo, con lo que dice el Acuerdo si difiere (sin tocar el objeto original). */
function conAcuerdo(estado: string, clave: string, m: Municipio): Municipio {
  const acuerdo = indiceDivergencias.get(`${estado}|${clave}`);
  return acuerdo ? { ...m, acuerdo } : m;
}

function municipioDelAcuerdo(a: { oficial: string; divisiones: string[] }): Municipio {
  return { id: "", nombre: normalizar(a.oficial), origen: "acuerdo",
           opciones: a.divisiones.map((d) => ({ id: "", etiqueta: d })) };
}

export function listarMunicipios(estado: string): Municipio[] | null {
  const clave = normalizar(estado);
  const e = catalogo.estados[clave];
  if (!e) return null;
  const lista: Municipio[] = Object.values(e.municipios);
  for (const a of complemento.ausentes?.[clave] ?? []) lista.push(municipioDelAcuerdo(a));
  return lista.sort((a, b) => a.nombre.localeCompare(b.nombre));
}

export function regionDeMunicipio(estado: string, municipio: string): Municipio | null {
  const clave = normalizar(estado);
  const e = catalogo.estados[clave];
  if (!e) return null;
  const nombre = normalizar(municipio);
  const directo = e.municipios[nombre];
  if (directo) return conAcuerdo(clave, nombre, directo);                  // el camino de siempre
  const k = `${clave}|${nombre}`;
  const alias = indiceAlias.get(k);
  if (alias && e.municipios[alias]) return conAcuerdo(clave, alias, e.municipios[alias]);
  const ausente = indiceAusentes.get(k);
  return ausente ? municipioDelAcuerdo(ausente) : null;
}

/**
 * Divisiones reales detrás de una etiqueta del desplegable de CFE.
 *
 * Las etiquetas compuestas no se pueden partir por texto: CFE elide el
 * prefijo compartido, así que "VALLE DE MEXICO CENTRO Y SUR" son Centro y Sur
 * del Valle de México, no una división llamada "SUR". La equivalencia la
 * aprende el scraper leyendo los encabezados que devuelve la página y la deja
 * en `expansiones`.
 */
export function expandirEtiqueta(etiqueta: string): string[] {
  const t = normalizar(etiqueta);
  return catalogo.expansiones?.[t] ?? [t];
}

/** Todas las divisiones posibles de un municipio. */
export function regionesDeMunicipio(m: Municipio): string[] {
  const opciones = m.opciones?.length
    ? m.opciones
    : m.region
      ? [{ id: m.region_id ?? "", etiqueta: m.region }]
      : [];
  const vistas = new Set<string>();
  for (const o of opciones) for (const r of expandirEtiqueta(o.etiqueta)) vistas.add(r);
  return [...vistas];
}

export function listarRegiones(): string[] {
  const s = new Set<string>();
  for (const r of Object.values(tarifas.registros)) s.add(r.region);
  for (const e of Object.values(catalogo.estados))
    for (const m of Object.values(e.municipios))
      for (const r of regionesDeMunicipio(m)) s.add(r);
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

/** Sistema de horario de una división tarifaria; null si no está en el mapa. */
export function sistemaDeDivision(region: string): ClaveSistema | null {
  const s = sistemasHorario.divisiones[normalizar(region)];
  return s && s in sistemasHorario.sistemas ? (s as ClaveSistema) : null;
}

/** La zona de horarios.json que corresponde a un sistema (se ubica por nombre). */
export function zonaDeSistema(clave: string): Zona | null {
  const ancla = sistemasHorario.sistemas[clave]?.zona_contiene;
  if (!ancla) return null;
  const a = normalizar(ancla);
  for (const z of Object.values(horarios.zonas)) {
    if (z.regiones.map(normalizar).includes(a)) return z;
  }
  return null;
}

/**
 * Zona de horarios de una división.
 *
 * Primero por el mapa oficial división -> sistema. Si el nombre no es una
 * división (p. ej. CENTRAL, NORESTE o SUR, nombres heredados que el portal
 * imprime en la zona del SIN y que ya se aceptaban) se cae al emparejamiento
 * por nombre de siempre, para no romper a quien ya los use.
 *
 * Deliberadamente NO hay un valor por omisión: una división desconocida
 * devuelve null y la consulta falla en vez de heredar en silencio el horario
 * del SIN.
 */
export function zonaDeRegion(region: string): Zona | null {
  const sistema = sistemaDeDivision(region);
  if (sistema) return zonaDeSistema(sistema);
  const r = normalizar(region);
  for (const z of Object.values(horarios.zonas)) {
    if (z.regiones.map(normalizar).includes(r)) return z;
  }
  return null;
}

/** Sistema (SIN/BC/BCS) al que pertenece una zona de horarios.json. */
export function sistemaDeZona(zona: Zona): ClaveSistema | null {
  const regiones = zona.regiones.map(normalizar);
  for (const [clave, def] of Object.entries(sistemasHorario.sistemas)) {
    if (regiones.includes(normalizar(def.zona_contiene))) return clave as ClaveSistema;
  }
  return null;
}

/**
 * Lo que el cliente necesita para no confundir los dos conceptos:
 *  - division: la división tarifaria (cargos); null si el nombre pedido es uno
 *    de los heredados (CENTRAL, NORESTE, SUR...) y no una división.
 *  - sistema_horario: SIN, BC o BCS.
 */
export function describirHorario(region: string): { division: string | null; sistema_horario: ClaveSistema | null } {
  const zona = zonaDeRegion(region);
  return {
    division: sistemaDeDivision(region) ? normalizar(region) : null,
    sistema_horario: zona ? sistemaDeZona(zona) : null,
  };
}

export const AVISO =
  "Datos capturados automáticamente del portal público de CFE. Este no es un " +
  "servicio oficial de CFE ni está afiliado a ella. La fuente autoritativa es " +
  "el portal de CFE; verifica ahí antes de usar estas cifras para facturación " +
  "o decisiones de inversión.";
