/**
 * Tipo de cambio pesos por dólar de Banxico (SIE), con historial en D1.
 *
 * Dos series del mismo valor:
 *   fix -> SF43718: FIX por fecha de determinación (el que usa la calculadora de Hollman).
 *   dof -> SF60653: el mismo FIX por fecha de publicación en el Diario Oficial (día hábil
 *          siguiente). Útil cuando un contrato cita "el tipo de cambio publicado en el DOF".
 *
 * Un cron diario lo consulta con el token del Worker (secreto BANXICO_TOKEN) y lo guarda;
 * las consultas leen de D1, nunca de Banxico. Si la tabla está vacía, el cron trae el
 * historial desde 2024; si no, los últimos 10 días (idempotente: no duplica).
 */
import { AVISO } from "./datos";

export const SERIES = {
  fix: { id: "SF43718", nombre: "FIX por fecha de determinación" },
  dof: { id: "SF60653", nombre: "FIX por fecha de publicación en el DOF" },
} as const;
export type ClaveSerie = keyof typeof SERIES;

const BANXICO = "https://www.banxico.org.mx/SieAPIRest/service/v1";
const INICIO_HISTORIAL = "2024-01-01";
const DIAS_AVISO = 5;

/** Superficie mínima de D1 que se usa (también la cumple el adaptador de pruebas). */
export interface Base {
  prepare(sql: string): { bind(...v: unknown[]): { first<T = Record<string, unknown>>(): Promise<T | null>; run(): Promise<unknown> } };
  batch(stmts: unknown[]): Promise<unknown>;
}

const iso = (d: Date) => d.toISOString().slice(0, 10);
/** "07/10/2026" -> "2026-10-07" */
const desdeBanxico = (f: string) => { const [d, m, a] = f.split("/"); return `${a}-${m}-${d}`; };

/** Consulta Banxico y guarda las dos series. Devuelve cuántos valores nuevos o corregidos guardó. */
export async function actualizarTipoCambio(db: Base, token: string | undefined, ahora: number, fetcher: typeof fetch = fetch) {
  if (!token) throw new Error("BANXICO_TOKEN no está configurado en tarifas-electricas-mx.");
  const hay = await db.prepare("SELECT max(fecha) AS f FROM tipo_cambio").bind().first<{ f: string | null }>();
  const hasta = iso(new Date(ahora));
  const desde = hay?.f ? iso(new Date(ahora - 10 * 86400000)) : INICIO_HISTORIAL;
  const ids = Object.values(SERIES).map((s) => s.id).join(",");
  const res = await fetcher(`${BANXICO}/series/${ids}/datos/${desde}/${hasta}`, { headers: { "Bmx-Token": token, accept: "application/json" } });
  if (!res.ok) throw new Error(`Banxico respondió ${res.status}.`);
  const json = (await res.json()) as { bmx?: { series?: { idSerie: string; datos?: { fecha: string; dato: string }[] }[] } };
  const filas: [string, string, number][] = [];
  for (const s of json.bmx?.series ?? []) {
    for (const d of s.datos ?? []) {
      const valor = Number(String(d.dato).replace(/,/g, ""));
      if (valor > 0) filas.push([s.idSerie, desdeBanxico(d.fecha), valor]);
    }
  }
  if (!filas.length) return { guardados: 0, desde, hasta };
  const sql = "INSERT INTO tipo_cambio (serie, fecha, valor, obtenido_en) VALUES (?, ?, ?, ?) " +
    "ON CONFLICT (serie, fecha) DO UPDATE SET valor = excluded.valor, obtenido_en = excluded.obtenido_en WHERE tipo_cambio.valor <> excluded.valor";
  for (let i = 0; i < filas.length; i += 50) {
    await db.batch(filas.slice(i, i + 50).map(([s, f, v]) => db.prepare(sql).bind(s, f, v, ahora)));
  }
  return { guardados: filas.length, desde, hasta };
}

/** Valor vigente en una fecha (el último publicado en o antes de ella) para una serie. */
export async function consultarTipoCambio(db: Base | undefined, args: Record<string, unknown>, ahora: number) {
  if (!db) return { error: "El tipo de cambio no está configurado en este servidor." };
  const clave = (args.serie ?? "fix") as ClaveSerie;
  if (!(clave in SERIES)) return { error: "serie debe ser fix o dof." };
  const hoy = iso(new Date(ahora));
  const fecha = args.fecha == null ? hoy : String(args.fecha);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(fecha) || Number.isNaN(Date.parse(fecha))) return { error: "fecha debe ir como AAAA-MM-DD." };
  const serie = SERIES[clave];
  const fila = await db.prepare("SELECT fecha, valor FROM tipo_cambio WHERE serie = ? AND fecha <= ? ORDER BY fecha DESC LIMIT 1")
    .bind(serie.id, fecha).first<{ fecha: string; valor: number }>();
  if (!fila) return { error: `No hay tipo de cambio ${serie.id} en o antes del ${fecha}.`, serie: clave };
  const dias = Math.floor((Date.parse(fecha) - Date.parse(fila.fecha)) / 86400000);
  return {
    serie: clave, id_serie: serie.id, descripcion: serie.nombre,
    fecha_solicitada: fecha, fecha: fila.fecha, valor: fila.valor,
    ...(dias > DIAS_AVISO ? { aviso_antiguedad: `El último valor es del ${fila.fecha} (${dias} días antes de la fecha pedida).` } : {}),
    fuente: "Banco de México, Sistema de Información Económica (SIE)",
    aviso: AVISO,
  };
}
