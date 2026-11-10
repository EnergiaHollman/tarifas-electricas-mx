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
import regionesDacJson from "../../data/regiones_dac.json";
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
  // Solo domésticas (1, 1A a 1F): escalones en kWh y, de la 1A a la 1F, los
  // cargos van por temporada en vez de en `cargos`.
  minimo_mensual_kwh?: number;
  escalones?: Escalon[];
  temporadas?: Record<string, { cargos: Record<string, number>; unidades: Record<string, string>;
                                escalones: Escalon[]; conceptos: Registro["conceptos"] }>;
};

export type Escalon = { nombre: string; desde_kwh: number; hasta_kwh: number | null; valor: number };

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
  // Las regiones de DAC (p. ej. "NORTE Y NORESTE") no son divisiones tarifarias.
  for (const r of Object.values(tarifas.registros)) if (ubicacionDe(r.tarifa) === "division") s.add(r.region);
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

/**
 * Qué se sabe de cada tarifa que el servidor puede ofrecer. Lo único que no
 * sale de los datos capturados: la descripción y si la tarifa tiene horarios
 * (base/intermedia/punta). Una tarifa sin horarios no lleva sistema_horario ni
 * división de horario en la respuesta: no le aplican.
 */
export type Ubicacion = "division" | "region_dac" | "nacional";

export const META_TARIFAS: Record<
  string,
  { descripcion: string; horarios: boolean; ubicacion: Ubicacion; estacional?: boolean; notas?: string[] }
> = {
  GDMTH: { descripcion: "Gran demanda en media tensión, horaria", horarios: true, ubicacion: "division" },
  GDMTO: { descripcion: "Gran demanda en media tensión, ordinaria", horarios: false, ubicacion: "division" },
  PDBT: { descripcion: "Pequeña demanda en baja tensión, hasta 25 kW-mes", horarios: false, ubicacion: "division" },
  DAC: {
    descripcion: "Doméstica de alto consumo",
    horarios: false,
    // Sus regiones no son las divisiones de GDMTH: ver regiones_dac.json.
    ubicacion: "region_dac",
    notas: [
      "Las seis regiones de DAC (Baja California, Baja California Sur, Central, Noroeste, Norte y " +
        "Noreste, Sur y Peninsular) no son las divisiones tarifarias de GDMTH.",
      "Solo la división NOROESTE tiene mapeo confirmado a su región de DAC. Para las demás divisiones " +
        "pasa region con la región de DAC que indica tu recibo (p. ej. region=CENTRAL).",
      "El cargo fijo de 2025-2026 (145.85 en septiembre de 2026) NO está validado contra un recibo real. " +
        "El único recibo de DAC disponible es de septiembre de 2019 en Noroeste, que el portal reproduce exacto.",
    ],
  },
};

/** Domésticas: precio nacional por escalones; de la 1A a la 1F, con temporada de verano. */
const NOTAS_DOMESTICAS = (estacional: boolean): string[] => [
  "Precio nacional: no depende de estado ni municipio.",
  ...(estacional
    ? [
        "Requiere inicio_verano (2 a 5: el mes en que comienza el verano en la localidad; el verano dura " +
          "seis meses seguidos) o temporada (verano | fuera_verano). El tamaño de los escalones cambia con la " +
          "temporada.",
      ]
    : []),
  "Los escalones están en kWh MENSUALES. Con facturación bimestral los límites se duplican; eso lo " +
    "aplica quien consulta, no estos datos.",
  "Los apoyos o subsidios domésticos no están en estos datos.",
  "Los precios se leen del portal de CFE y este servicio no los ha validado contra recibos reales.",
];
const DOMESTICAS: [string, string][] = [
  ["1", "Doméstica, sin temporada de verano"],
  ["1A", "Doméstica, localidades con temperatura media mínima en verano de 25 °C"],
  ["1B", "Doméstica, localidades con temperatura media mínima en verano de 28 °C"],
  ["1C", "Doméstica, localidades con temperatura media mínima en verano de 30 °C"],
  ["1D", "Doméstica, localidades con temperatura media mínima en verano de 31 °C"],
  ["1E", "Doméstica, localidades con temperatura media mínima en verano de 32 °C"],
  ["1F", "Doméstica, localidades con temperatura media mínima en verano de 33 °C"],
];
for (const [clave, descripcion] of DOMESTICAS) {
  META_TARIFAS[clave] = {
    descripcion, horarios: false, ubicacion: "nacional", estacional: clave !== "1",
    notas: NOTAS_DOMESTICAS(clave !== "1"),
  };
}

export function esEstacional(tarifa: string): boolean {
  return META_TARIFAS[normalizar(tarifa)]?.estacional ?? false;
}

/** División tarifaria -> región de DAC. Solo divisiones confirmadas. */
export const regionesDac = regionesDacJson as unknown as {
  fuente: string;
  regiones_dac: string[];
  confirmadas: Record<string, { region_dac: string; confirmacion: string }>;
};

export function ubicacionDe(tarifa: string): Ubicacion {
  return META_TARIFAS[normalizar(tarifa)]?.ubicacion ?? "division";
}

export function tieneHorarios(tarifa: string): boolean {
  return META_TARIFAS[normalizar(tarifa)]?.horarios ?? false;
}

export type ResumenTarifa = {
  tarifa: string;
  descripcion: string | null;
  horarios: boolean;
  ubicacion: Ubicacion;
  notas?: string[];
  regiones: string[];
  periodo_desde: string;
  periodo_hasta: string;
  registros: number;
};

/** Las tarifas que tienen al menos un registro capturado, con su cobertura. */
export function tarifasConDatos(): ResumenTarifa[] {
  const por = new Map<string, { regiones: Set<string>; periodos: string[] }>();
  for (const [k, r] of Object.entries(tarifas.registros)) {
    const e = por.get(r.tarifa) ?? { regiones: new Set<string>(), periodos: [] };
    e.regiones.add(r.region);
    e.periodos.push(k.slice(k.lastIndexOf("|") + 1));
    por.set(r.tarifa, e);
  }
  return [...por.entries()]
    .map(([tarifa, e]) => {
      const ps = e.periodos.sort();
      return {
        tarifa,
        descripcion: META_TARIFAS[tarifa]?.descripcion ?? null,
        horarios: tieneHorarios(tarifa),
        ubicacion: ubicacionDe(tarifa),
        ...(META_TARIFAS[tarifa]?.notas ? { notas: META_TARIFAS[tarifa].notas } : {}),
        regiones: [...e.regiones].sort(),
        periodo_desde: ps[0],
        periodo_hasta: ps[ps.length - 1],
        registros: ps.length,
      };
    })
    .sort((a, b) => a.tarifa.localeCompare(b.tarifa));
}

export const AVISO =
  "Datos capturados automáticamente del portal público de CFE. Este no es un " +
  "servicio oficial de CFE ni está afiliado a ella. La fuente autoritativa es " +
  "el portal de CFE; verifica ahí antes de usar estas cifras para facturación " +
  "o decisiones de inversión.";
