/**
 * Tasas de referencia de Banxico (SIE), con historial en D1.
 *
 *   fondeo -> SF331451: TIIE de Fondeo a un día hábil bancario (en % anual). Es la tasa de referencia vigente para
 *             los financiamientos nuevos (Banxico retira la TIIE a 28, 91 y 182 días en operaciones nuevas).
 *
 * Mismo esquema que el tipo de cambio: un cron diario la consulta con el token del Worker (secreto BANXICO_TOKEN) y la
 * guarda; las consultas leen de D1, nunca de Banxico. Si la tabla está vacía trae el historial desde 2024; si no, los
 * últimos 10 días (idempotente: no duplica). El valor «vigente en una fecha» es el último publicado en o antes de ella.
 */

export const SERIES_TASAS = {
  fondeo: { id: "SF331451", nombre: "TIIE de Fondeo a un día hábil bancario (% anual)" },
} as const;
export type ClaveTasa = keyof typeof SERIES_TASAS;

const BANXICO = "https://www.banxico.org.mx/SieAPIRest/service/v1";
const INICIO_HISTORIAL = "2024-01-01";
const DIAS_AVISO = 7;
/** El dato viene de Banxico, no de CFE: aviso propio en lugar del general de tarifas. */
export const AVISO_TASAS =
  "Datos descargados automáticamente de la API pública del SIE de Banco de México. Este no " +
  "es un servicio oficial de Banxico ni está afiliado a él. La fuente autoritativa es el SIE " +
  "de Banxico; verifica ahí antes de usar estas cifras en contratos o créditos.";

/** Superficie mínima de D1 que se usa (también la cumple el adaptador de pruebas). */
export interface BaseTasas {
  prepare(sql: string): { bind(...v: unknown[]): { first<T = Record<string, unknown>>(): Promise<T | null>; run(): Promise<unknown> } };
  batch(stmts: unknown[]): Promise<unknown>;
}

const iso = (d: Date) => d.toISOString().slice(0, 10);
/** "07/10/2026" -> "2026-10-07" */
const desdeBanxico = (f: string) => { const [d, m, a] = f.split("/"); return `${a}-${m}-${d}`; };

/** Consulta Banxico y guarda las series. Devuelve cuántos valores nuevos o corregidos guardó. */
export async function actualizarTasas(db: BaseTasas, token: string | undefined, ahora: number, fetcher: typeof fetch = fetch) {
  if (!token) throw new Error("BANXICO_TOKEN no está configurado en tarifas-electricas-mx.");
  const hay = await db.prepare("SELECT max(fecha) AS f FROM tasa_referencia").bind().first<{ f: string | null }>();
  const hasta = iso(new Date(ahora));
  const desde = hay?.f ? iso(new Date(ahora - 10 * 86400000)) : INICIO_HISTORIAL;
  const ids = Object.values(SERIES_TASAS).map((s) => s.id).join(",");
  const res = await fetcher(`${BANXICO}/series/${ids}/datos/${desde}/${hasta}`, { headers: { "Bmx-Token": token, accept: "application/json" } });
  if (!res.ok) throw new Error(`Banxico respondió ${res.status}.`);
  const json = (await res.json()) as { bmx?: { series?: { idSerie: string; datos?: { fecha: string; dato: string }[] }[] } };
  const filas: [string, string, number][] = [];
  for (const s of json.bmx?.series ?? []) {
    for (const d of s.datos ?? []) {
      const valor = Number(String(d.dato).replace(/,/g, ""));
      // Una tasa puede ser cero, pero «N/E» (no existe) no es un dato.
      if (String(d.dato).trim() !== "" && Number.isFinite(valor) && valor >= 0) filas.push([s.idSerie, desdeBanxico(d.fecha), valor]);
    }
  }
  if (!filas.length) return { guardados: 0, desde, hasta };
  const sql = "INSERT INTO tasa_referencia (serie, fecha, valor, obtenido_en) VALUES (?, ?, ?, ?) " +
    "ON CONFLICT (serie, fecha) DO UPDATE SET valor = excluded.valor, obtenido_en = excluded.obtenido_en WHERE tasa_referencia.valor <> excluded.valor";
  for (let i = 0; i < filas.length; i += 50) {
    await db.batch(filas.slice(i, i + 50).map(([s, f, v]) => db.prepare(sql).bind(s, f, v, ahora)));
  }
  return { guardados: filas.length, desde, hasta };
}

/** Valor vigente en una fecha (el último publicado en o antes de ella) para una serie. */
export async function consultarTasa(db: BaseTasas | undefined, args: Record<string, unknown>, ahora: number) {
  if (!db) return { error: "Las tasas de referencia no están configuradas en este servidor." };
  const clave = (args.serie ?? "fondeo") as ClaveTasa;
  if (!(clave in SERIES_TASAS)) return { error: "serie debe ser fondeo." };
  const hoy = iso(new Date(ahora));
  const fecha = args.fecha == null ? hoy : String(args.fecha);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(fecha) || Number.isNaN(Date.parse(fecha))) return { error: "fecha debe ir como AAAA-MM-DD." };
  const serie = SERIES_TASAS[clave];
  const fila = await db.prepare("SELECT fecha, valor FROM tasa_referencia WHERE serie = ? AND fecha <= ? ORDER BY fecha DESC LIMIT 1")
    .bind(serie.id, fecha).first<{ fecha: string; valor: number }>();
  if (!fila) return { error: `No hay tasa ${serie.id} en o antes del ${fecha}.`, serie: clave };
  const dias = Math.floor((Date.parse(fecha) - Date.parse(fila.fecha)) / 86400000);
  return {
    serie: clave, id_serie: serie.id, descripcion: serie.nombre,
    fecha_solicitada: fecha, fecha: fila.fecha, valor: fila.valor,
    ...(dias > DIAS_AVISO ? { aviso_antiguedad: `El último valor es del ${fila.fecha} (${dias} días antes de la fecha pedida).` } : {}),
    fuente: "Banco de México, Sistema de Información Económica (SIE)",
    aviso: AVISO_TASAS,
  };
}
