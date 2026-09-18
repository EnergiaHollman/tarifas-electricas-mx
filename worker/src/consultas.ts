/**
 * La lógica de consulta, compartida entre REST y MCP para que ambos den
 * exactamente la misma respuesta.
 */
import { franjas, periodoEn, temporadaDe, tipoDia } from "./calendario";
import {
  AVISO,
  catalogo,
  regionesDeMunicipio,
  listarEstados,
  listarRegiones,
  normalizar,
  obtenerTarifa,
  periodosDe,
  regionDeMunicipio,
  tarifas,
  zonaDeRegion,
} from "./datos";

type Args = Record<string, any>;

function entero(v: unknown): number | null {
  const n = typeof v === "string" ? parseInt(v, 10) : typeof v === "number" ? v : NaN;
  return Number.isFinite(n) ? n : null;
}

/** Resuelve la región desde región explícita o desde estado + municipio. */
function resolverRegion(args: Args) {
  if (args.region) {
    return { region: normalizar(String(args.region)), regiones: [normalizar(String(args.region))],
             via: "region" as const };
  }
  if (args.estado && args.municipio) {
    const m = regionDeMunicipio(String(args.estado), String(args.municipio));
    if (!m) {
      const e = catalogo.estados[normalizar(String(args.estado))];
      return {
        error: e
          ? `El municipio "${args.municipio}" no está en el catálogo de ${e.nombre}.`
          : `El estado "${args.estado}" no está en el catálogo.`,
        sugerencia: e
          ? "El catálogo puede estar incompleto; también puedes consultar por región."
          : `Estados con catálogo: ${listarEstados().join(", ") || "ninguno todavía"}.`,
      };
    }
    const regiones = regionesDeMunicipio(m);
    return {
      region: regiones[0],
      regiones,                       // dos cuando CFE atiende con dos divisiones
      via: "municipio" as const,
      municipio: m.nombre,
      estado: catalogo.estados[normalizar(String(args.estado))].nombre,
    };
  }
  return { error: "Falta la ubicación: manda region, o estado y municipio." };
}

export function consultarTarifa(args: Args) {
  const anio = entero(args.anio);
  const mes = entero(args.mes);
  if (anio === null || mes === null) return { error: "Faltan anio y mes." };
  if (mes < 1 || mes > 12) return { error: "El mes debe ir de 1 a 12." };

  const ubic = resolverRegion(args);
  if ("error" in ubic) return ubic;

  const tarifa = normalizar(String(args.tarifa ?? "GDMTH"));

  // Municipio que CFE atiende con dos divisiones: se devuelven las dos, porque
  // cuál aplica depende del punto de suministro y solo el recibo lo dice.
  if (ubic.regiones.length > 1) {
    const resultados = ubic.regiones
      .map((reg) => {
        const t = obtenerTarifa(tarifa, reg, anio, mes);
        return t ? { region: reg, cargos: t.cargos, unidades: t.unidades,
                     periodo_cfe: t.periodo_cfe, fecha_captura: t.fecha_captura } : null;
      })
      .filter(Boolean);
    if (resultados.length) {
      return {
        tarifa, estado: ubic.estado, municipio: ubic.municipio,
        regiones: ubic.regiones, anio, mes, resultados,
        nota: "CFE ofrece más de una división tarifaria para este municipio. " +
              "Cuál aplica depende del punto de suministro; confírmalo en el recibo.",
        aviso: AVISO,
      };
    }
  }

  const r = obtenerTarifa(tarifa, ubic.region, anio, mes);
  if (!r) {
    const disponibles = periodosDe(tarifa, ubic.region);
    return {
      error: `No hay datos capturados de ${tarifa} en ${ubic.region} para ${anio}-${String(mes).padStart(2, "0")}.`,
      region: ubic.region,
      periodos_disponibles: disponibles.length > 40
        ? [disponibles[0], "...", disponibles[disponibles.length - 1]]
        : disponibles,
      aviso: AVISO,
    };
  }

  return {
    tarifa: r.tarifa,
    region: r.region,
    ...(ubic.via === "municipio" ? { estado: ubic.estado, municipio: ubic.municipio } : {}),
    anio: r.anio,
    mes: r.mes,
    periodo_cfe: r.periodo_cfe,
    cargos: r.cargos,
    unidades: r.unidades,
    conceptos: r.conceptos,
    fuente: r.fuente,
    fecha_captura: r.fecha_captura,
    aviso: AVISO,
  };
}

export function consultarHorarios(args: Args) {
  const ubic = resolverRegion(args);
  if ("error" in ubic) return ubic;

  const texto = String(args.fecha ?? "");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(texto)) return { error: "fecha debe ir como AAAA-MM-DD." };
  const fecha = new Date(`${texto}T00:00:00Z`);
  if (Number.isNaN(fecha.getTime())) return { error: `fecha inválida: ${texto}` };

  const zona = zonaDeRegion(ubic.region);
  if (!zona) {
    return {
      error: `Región desconocida: ${ubic.region}.`,
      regiones: listarRegiones(),
    };
  }

  const temporada = temporadaDe(zona, fecha);
  if (!temporada) return { error: "No se pudo determinar la temporada para esa zona." };
  const t = zona.temporadas[temporada];
  const tipo = tipoDia(fecha);
  const dia = t.dias[tipo];

  let enHora: Record<string, unknown> | undefined;
  if (args.hora) {
    const m = /^(\d{1,2}):(\d{2})$/.exec(String(args.hora));
    if (!m) return { error: "hora debe ir como HH:MM." };
    const minutos = parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
    enHora = { hora: String(args.hora), periodo: periodoEn(t.dias, tipo, minutos) };
  }

  return {
    region: ubic.region,
    ...(ubic.via === "municipio" ? { estado: ubic.estado, municipio: ubic.municipio } : {}),
    zona: zona.zona,
    fecha: texto,
    temporada,
    vigencia_temporada: t.vigencia,
    tipo_dia: tipo,
    franjas: franjas(dia),
    ...(enHora ? { consulta: enHora } : {}),
    nota:
      "Los días de descanso obligatorio del artículo 74 de la LFT, salvo la " +
      "fracción IX, se tratan como domingo.",
    fuente: zonaFuente(),
    aviso: AVISO,
  };
}

function zonaFuente() {
  return tarifas.fuente;
}

export function resumenRegiones() {
  const regiones = listarRegiones().map((r) => ({
    region: r,
    zona: zonaDeRegion(r)?.zona ?? null,
    periodos: periodosDe("GDMTH", r).length,
  }));
  return {
    regiones,
    estados_en_catalogo: listarEstados(),
    catalogo_parcial: catalogo.parcial === true,
    tarifas_actualizadas: tarifas.actualizado,
    total_registros: Object.keys(tarifas.registros).length,
    aviso: AVISO,
  };
}
