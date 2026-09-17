/**
 * Calendario de la tarifa: temporada, tipo de día y periodo tarifario.
 *
 * Las reglas de temporada no están codificadas aquí: vienen en horarios.json
 * tal como CFE las publica, y este módulo solo las evalúa. Si CFE cambia una
 * vigencia, se actualiza el JSON y no hay que tocar código.
 */

export type Regla =
  | { tipo: "fijo"; mes: number; dia: number; desplazamiento: number }
  | { tipo: "ultimo_dia_semana"; mes: number; dia_semana: number; desplazamiento: number }
  | { tipo: "n_dia_semana"; n: number; mes: number; dia_semana: number; desplazamiento: number };

export type Temporada = {
  vigencia: string;
  regla: { inicio: Regla; fin: Regla } | null;
  dias: Record<string, { base: number[][]; intermedia: number[][]; punta: number[][] }>;
};

export type Zona = {
  zona: string;
  regiones: string[];
  temporadas: Record<string, Temporada>;
};

const DIA_MS = 86400000;

/** Día de la semana estilo Python: lunes 0 ... domingo 6. */
function dow(d: Date): number {
  return (d.getUTCDay() + 6) % 7;
}

export function fechaUTC(anio: number, mes: number, dia: number): Date {
  return new Date(Date.UTC(anio, mes - 1, dia));
}

export function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Resuelve una regla a una fecha concreta dentro de un año. */
export function resolver(regla: Regla, anio: number): Date {
  let d: Date;
  if (regla.tipo === "fijo") {
    d = fechaUTC(anio, regla.mes, regla.dia);
  } else if (regla.tipo === "ultimo_dia_semana") {
    d = fechaUTC(anio, regla.mes + 1, 1);
    d = new Date(d.getTime() - DIA_MS); // último día del mes
    while (dow(d) !== regla.dia_semana) d = new Date(d.getTime() - DIA_MS);
  } else {
    d = fechaUTC(anio, regla.mes, 1);
    while (dow(d) !== regla.dia_semana) d = new Date(d.getTime() + DIA_MS);
    d = new Date(d.getTime() + (regla.n - 1) * 7 * DIA_MS);
  }
  return new Date(d.getTime() + (regla.desplazamiento || 0) * DIA_MS);
}

/**
 * Temporada vigente en una fecha. Se evalúa el verano: si la fecha cae en su
 * rango, es verano; si no, invierno. El verano nunca cruza el fin de año, lo
 * que hace la comparación directa.
 */
export function temporadaDe(zona: Zona, fecha: Date): string | null {
  const verano = zona.temporadas["verano"];
  if (!verano?.regla) return null;
  const anio = fecha.getUTCFullYear();
  const ini = resolver(verano.regla.inicio, anio);
  const fin = resolver(verano.regla.fin, anio);
  return fecha >= ini && fecha <= fin ? "verano" : "invierno";
}

/**
 * Días de descanso obligatorio del artículo 74 de la LFT, salvo la fracción IX
 * (jornada electoral), que la tarifa excluye expresamente. La tarifa los trata
 * como domingo.
 */
export function festivos(anio: number): string[] {
  const nEsimoLunes = (mes: number, n: number) => {
    let d = fechaUTC(anio, mes, 1);
    while (dow(d) !== 0) d = new Date(d.getTime() + DIA_MS);
    return new Date(d.getTime() + (n - 1) * 7 * DIA_MS);
  };
  const f = [
    fechaUTC(anio, 1, 1),
    nEsimoLunes(2, 1), // conmemoración del 5 de febrero
    nEsimoLunes(3, 3), // conmemoración del 21 de marzo
    fechaUTC(anio, 5, 1),
    fechaUTC(anio, 9, 16),
    nEsimoLunes(11, 3), // conmemoración del 20 de noviembre
    fechaUTC(anio, 12, 25),
  ];
  if (anio % 6 === 0) f.push(fechaUTC(anio, 12, 1)); // transmisión del Poder Ejecutivo
  return f.map(iso).sort();
}

export function tipoDia(fecha: Date): "habil" | "sabado" | "domingo" {
  if (festivos(fecha.getUTCFullYear()).includes(iso(fecha))) return "domingo";
  const w = dow(fecha);
  if (w === 6) return "domingo";
  if (w === 5) return "sabado";
  return "habil";
}

/** Periodo tarifario a una hora dada, en minutos desde medianoche. */
export function periodoEn(
  dias: Record<string, { base: number[][]; intermedia: number[][]; punta: number[][] }>,
  tipo: string,
  minutos: number,
): string | null {
  const d = dias[tipo];
  if (!d) return null;
  for (const p of ["punta", "intermedia", "base"] as const) {
    for (const [ini, fin] of d[p]) {
      if (minutos >= ini && minutos < fin) return p;
    }
  }
  return null;
}

/** Los intervalos de un día, ordenados, como texto legible. */
export function franjas(d: { base: number[][]; intermedia: number[][]; punta: number[][] }) {
  const hhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
  const todas: { periodo: string; inicio: string; fin: string; desde_min: number }[] = [];
  for (const p of ["base", "intermedia", "punta"] as const) {
    for (const [ini, fin] of d[p]) {
      todas.push({ periodo: p, inicio: hhmm(ini), fin: hhmm(fin === 1440 ? 1440 : fin), desde_min: ini });
    }
  }
  return todas.sort((a, b) => a.desde_min - b.desde_min).map(({ desde_min, ...r }) => r);
}
