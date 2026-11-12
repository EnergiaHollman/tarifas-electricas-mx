/**
 * La lógica de consulta, compartida entre REST y MCP para que ambos den
 * exactamente la misma respuesta.
 */
import { festivos, franjas, iso, periodoEn, resolver, temporadaDe, tipoDia } from "./calendario";
import {
  AVISO,
  type Escalon,
  type Registro,
  catalogo,
  describirHorario,
  esEstacional,
  regionesDeMunicipio,
  listarEstados,
  listarRegiones,
  normalizar,
  obtenerTarifa,
  energiaDof,
  validacionDe,
  DOMESTICAS_VALIDADAS,
  periodosDe,
  regionDeMunicipio,
  regionesDac,
  tarifas,
  tarifasConDatos,
  tieneHorarios,
  ubicacionDe,
  zonaDeRegion,
} from "./datos";

type Args = Record<string, any>;

function entero(v: unknown): number | null {
  const n = typeof v === "string" ? parseInt(v, 10) : typeof v === "number" ? v : NaN;
  return Number.isFinite(n) ? n : null;
}

/** Resuelve la región desde región explícita o desde estado + municipio. */
const NOTA_MUNICIPIO_ACUERDO =
  "Este municipio no aparece en el desplegable del portal de CFE; su división sale de la tabla " +
  "oficial del numeral 5.9 del Acuerdo CNE CT/11.SE/8-2025 (tarifas 2026).";

const NOTA_DIVISION =
  "El portal de CFE y el numeral 5.9 del Acuerdo CNE CT/11.SE/8-2025 no coinciden en la división de este " +
  "municipio. La respuesta sigue al portal; en divisiones_segun_acuerdo va lo que dice el Acuerdo. Si tu " +
  "recibo indica otra división, consúltala con el parámetro region.";

/** estado y municipio de la respuesta, más las advertencias que apliquen (solo cuando aplican). */
function datosMunicipio(ubic: { via?: string; estado?: string; municipio?: string; origen?: string; acuerdo?: string[] }) {
  if (ubic.via !== "municipio") return {};
  return {
    estado: ubic.estado, municipio: ubic.municipio,
    ...(ubic.origen === "acuerdo" ? { nota_municipio: NOTA_MUNICIPIO_ACUERDO } : {}),
    ...(ubic.acuerdo ? { divisiones_segun_acuerdo: ubic.acuerdo, nota_division: NOTA_DIVISION } : {}),
  };
}

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
      origen: m.origen,
      acuerdo: m.acuerdo,
      estado: catalogo.estados[normalizar(String(args.estado))].nombre,
    };
  }
  return { error: "Falta la ubicación: manda region, o estado y municipio." };
}

/** CFE no publica tarifas fuera de este rango; sirve para dar un error claro
 * en vez de un genérico "no hay datos" cuando el año es obviamente basura. */
function anioValido(anio: number): boolean {
  return anio >= 2000 && anio <= 2100;
}

export function consultarTarifa(args: Args) {
  const anio = entero(args.anio);
  const mes = entero(args.mes);
  if (anio === null || mes === null) return { error: "Faltan anio y mes." };
  if (mes < 1 || mes > 12) return { error: "El mes debe ir de 1 a 12." };
  if (!anioValido(anio)) return { error: "El año debe ser un número de cuatro dígitos razonable." };

  const tarifa = normalizar(String(args.tarifa ?? "GDMTH"));
  const conDatos = tarifasConDatos().map((t) => t.tarifa);
  if (!conDatos.includes(tarifa)) {
    return {
      error: `La tarifa "${tarifa}" no existe o todavía no tiene datos capturados.`,
      tarifas_disponibles: conDatos,
      aviso: AVISO,
    };
  }
  // Antes de resolver la ubicación: DAC se ubica por región de DAC, no por
  // división, y las domésticas no llevan ubicación.
  if (ubicacionDe(tarifa) === "region_dac") return consultarDac(args, tarifa, anio, mes);
  if (ubicacionDe(tarifa) === "nacional") return consultarDomestica(args, tarifa, anio, mes);

  const ubic = resolverRegion(args);
  if ("error" in ubic) return ubic;

  // Las tarifas sin horarios no llevan sistema_horario ni división de horario.
  const horario = (reg: string) => (tieneHorarios(tarifa) ? describirHorario(reg) : {});

  // Municipio que CFE atiende con dos divisiones: se devuelven las dos, porque
  // cuál aplica depende del punto de suministro y solo el recibo lo dice.
  if (ubic.regiones.length > 1) {
    const resultados = ubic.regiones
      .map((reg) => {
        const t = obtenerTarifa(tarifa, reg, anio, mes);
        return t ? { region: reg, ...horario(reg), cargos: t.cargos, unidades: t.unidades,
                     periodo_cfe: t.periodo_cfe, ...energiaDof(tarifa, reg, anio, mes), ...validacionDe(tarifa, reg, anio, mes),
                     fecha_captura: t.fecha_captura } : null;
      })
      .filter(Boolean);
    if (resultados.length) {
      return {
        tarifa, ...datosMunicipio(ubic),
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
    // Aditivo: `region` se queda como siempre; estos dos separan los conceptos
    // (cargos por DIVISIÓN, horarios por SISTEMA interconectado).
    ...horario(r.region),
    ...datosMunicipio(ubic),
    anio: r.anio,
    mes: r.mes,
    periodo_cfe: r.periodo_cfe,
    cargos: r.cargos,
    unidades: r.unidades,
    conceptos: r.conceptos,
    ...energiaDof(tarifa, r.region, r.anio, r.mes),
    ...validacionDe(tarifa, r.region, r.anio, r.mes),
    fuente: r.fuente,
    fecha_captura: r.fecha_captura,
    aviso: AVISO,
  };
}

/**
 * DAC. Sus regiones (Central, Noroeste, Norte y Noreste, Sur y Peninsular,
 * Baja California, Baja California Sur) no son las divisiones de GDMTH.
 *
 *  - region=<región de DAC>: se usa tal cual, es la que el usuario dice.
 *  - estado + municipio (o una división por region=): solo si esa división está
 *    CONFIRMADA en regiones_dac.json. Si no, error claro: no se adivina.
 */
function consultarDac(args: Args, tarifa: string, anio: number, mes: number) {
  const disponibles = regionesDac.regiones_dac;
  const confirmadas = Object.keys(regionesDac.confirmadas).sort();
  let regionDac: string;
  let via: "region_dac" | "division";
  let ubic: ReturnType<typeof resolverRegion> | null = null;

  const sinConfirmar = (division: string) => ({
    error:
      `La región de DAC de la división ${division} no está confirmada, y no se adivina. ` +
      "Pasa region con la región de DAC que indica tu recibo.",
    division,
    regiones_dac: disponibles,
    divisiones_confirmadas: confirmadas,
    aviso: AVISO,
  });

  if (args.region) {
    const pedida = normalizar(String(args.region));
    if (disponibles.includes(pedida)) {
      regionDac = pedida;
      via = "region_dac";
    } else if (regionesDac.confirmadas[pedida]) {
      regionDac = regionesDac.confirmadas[pedida].region_dac;
      via = "division";
    } else if (listarRegiones().includes(pedida)) {
      return sinConfirmar(pedida);
    } else {
      return { error: `"${pedida}" no es una región de DAC.`, regiones_dac: disponibles, aviso: AVISO };
    }
  } else {
    ubic = resolverRegion(args);
    if ("error" in ubic) return ubic;
    const destinos = new Set<string>();
    for (const division of ubic.regiones) {
      const c = regionesDac.confirmadas[division];
      if (!c) return sinConfirmar(division);
      destinos.add(c.region_dac);
    }
    if (destinos.size !== 1) {
      return {
        error: "El municipio cae en divisiones con distinta región de DAC; cuál aplica depende del punto " +
               "de suministro. Pasa region con la región de DAC de tu recibo.",
        divisiones: ubic.regiones, regiones_dac: [...destinos], aviso: AVISO,
      };
    }
    regionDac = [...destinos][0];
    via = "division";
  }

  const r = obtenerTarifa(tarifa, regionDac, anio, mes);
  if (!r) {
    const periodos = periodosDe(tarifa, regionDac);
    return {
      error: `No hay datos capturados de ${tarifa} en ${regionDac} para ${anio}-${String(mes).padStart(2, "0")}.`,
      region: regionDac,
      periodos_disponibles: periodos.length > 40 ? [periodos[0], "...", periodos[periodos.length - 1]] : periodos,
      aviso: AVISO,
    };
  }
  return {
    tarifa: r.tarifa,
    region: r.region,
    via_region: via,
    ...(ubic ? datosMunicipio(ubic) : {}),
    anio: r.anio,
    mes: r.mes,
    periodo_cfe: r.periodo_cfe,
    cargos: r.cargos,
    unidades: r.unidades,
    conceptos: r.conceptos,
    fuente: r.fuente,
    fecha_captura: r.fecha_captura,
    nota:
      "region es la región de DAC, no una división de GDMTH. El cargo fijo de 2025-2026 no está " +
      "validado contra un recibo real (ver /v1/tarifas).",
    aviso: AVISO,
  };
}

/**
 * Domésticas (1, 1A a 1F). No llevan ubicación: el precio es nacional. De la 1A
 * a la 1F depende de la temporada, y quien consulta la dice explícitamente: con
 * inicio_verano (2 a 5, el mes en que comienza el verano; el verano son seis
 * meses seguidos) o con temporada. Si da las dos, tienen que coincidir. No se
 * infiere nada de la localidad.
 */
function consultarDomestica(args: Args, tarifa: string, anio: number, mes: number) {
  const r = obtenerTarifa(tarifa, "NACIONAL", anio, mes);
  if (!r) {
    const periodos = periodosDe(tarifa, "NACIONAL");
    return {
      error: `No hay datos capturados de ${tarifa} para ${anio}-${String(mes).padStart(2, "0")}.`,
      periodos_disponibles: periodos.length > 40 ? [periodos[0], "...", periodos[periodos.length - 1]] : periodos,
      aviso: AVISO,
    };
  }

  let temporada: string | null = null;
  let inicio: number | null = null;
  let bloque: { cargos: Record<string, number>; unidades: Record<string, string>; escalones: Escalon[];
                conceptos: Registro["conceptos"] } = r as any;

  if (esEstacional(tarifa)) {
    if (args.inicio_verano !== undefined && args.inicio_verano !== null && args.inicio_verano !== "") {
      inicio = entero(args.inicio_verano);
      if (inicio === null || inicio < 2 || inicio > 5) {
        return { error: "inicio_verano debe ser el mes en que comienza el verano, de 2 (febrero) a 5 (mayo).",
                 aviso: AVISO };
      }
    }
    let pedida: string | null = null;
    if (args.temporada) {
      const t = normalizar(String(args.temporada)).replace(/ /g, "_");
      if (t !== "VERANO" && t !== "FUERA_VERANO" && t !== "FUERA_DE_VERANO") {
        return { error: 'temporada debe ser "verano" o "fuera_verano".', aviso: AVISO };
      }
      pedida = t === "VERANO" ? "verano" : "fuera_verano";
    }
    const derivada = inicio === null ? null : inicio <= mes && mes <= inicio + 5 ? "verano" : "fuera_verano";
    if (derivada && pedida && derivada !== pedida) {
      return {
        error: `inicio_verano=${inicio} y temporada=${pedida} se contradicen para el mes ${mes}: ` +
               `con ese inicio el mes es ${derivada}.`,
        aviso: AVISO,
      };
    }
    temporada = derivada ?? pedida;
    if (!temporada) {
      return {
        error: `${tarifa} depende de la temporada: pasa inicio_verano (2 a 5, el mes en que comienza el ` +
               "verano en la localidad) o temporada (verano | fuera_verano).",
        aviso: AVISO,
      };
    }
    const b = r.temporadas?.[temporada];
    if (!b) {
      return {
        error: `${tarifa} no tiene temporada ${temporada} publicada para ${anio}-${String(mes).padStart(2, "0")}.`,
        temporadas_disponibles: Object.keys(r.temporadas ?? {}),
        nota: "Con los meses de inicio de verano que ofrece CFE (febrero a mayo), enero, noviembre y " +
              "diciembre son siempre fuera de verano, y mayo, junio y julio siempre verano.",
        aviso: AVISO,
      };
    }
    bloque = b;
  }

  return {
    tarifa: r.tarifa,
    region: r.region,
    anio: r.anio,
    mes: r.mes,
    periodo_cfe: r.periodo_cfe,
    ...(temporada ? { temporada } : {}),
    ...(inicio !== null ? { inicio_verano: inicio } : {}),
    cargos: bloque.cargos,
    unidades: bloque.unidades,
    escalones: bloque.escalones,
    conceptos: bloque.conceptos,
    minimo_mensual_kwh: r.minimo_mensual_kwh,
    periodo_facturacion: "mensual",
    ...validacionDe(tarifa, r.region, r.anio, r.mes, temporada),
    fuente: r.fuente,
    fecha_captura: r.fecha_captura,
    nota:
      "Escalones en kWh mensuales (con facturación bimestral los límites se duplican: lo aplica quien " +
      "consulta). Los apoyos o subsidios no están incluidos. " +
      (DOMESTICAS_VALIDADAS.has(r.tarifa)
        ? "validado y bloques_validados dicen qué se reprodujo con recibos reales (ver /v1/tarifas)."
        : "Precios sin validar contra recibos reales."),
    aviso: AVISO,
  };
}

/**
 * Qué tarifas se pueden consultar y con qué cobertura, para que un cliente no
 * tenga que adivinar. anio y mes son el mes de las cuotas que CFE publica en su
 * portal ("Cuotas aplicables en el mes de X"), servido tal cual.
 */
export function listarTarifas() {
  return {
    tarifas: tarifasConDatos().map((t) => ({
      ...t,
      parametros:
        t.ubicacion === "region_dac"
          ? "anio, mes y region (una región de DAC), o estado + municipio de una división confirmada"
          : t.ubicacion === "nacional"
            ? esEstacional(t.tarifa)
              ? "anio, mes e inicio_verano (2 a 5) o temporada (verano | fuera_verano); sin ubicación"
              : "anio y mes; sin ubicación"
            : "anio, mes y ubicación (region, o estado + municipio)",
    })),
    nota_mes:
      "anio y mes son el mes de las cuotas publicadas por CFE, sin ajustes. Cómo se " +
      "corresponde con el mes de consumo o de facturación de un recibo se valida aparte " +
      "contra recibos reales; no se asume aquí.",
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
    const hh = parseInt(m[1], 10);
    const mm = parseInt(m[2], 10);
    if (hh > 23 || mm > 59) return { error: "hora debe estar entre 00:00 y 23:59." };
    const minutos = hh * 60 + mm;
    enHora = { hora: String(args.hora), periodo: periodoEn(t.dias, tipo, minutos) };
  }

  return {
    region: ubic.region,
    ...describirHorario(ubic.region),
    ...datosMunicipio(ubic),
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

/**
 * Calendario completo de un año para una región: rango del verano, festivos
 * que se tratan como domingo y franjas por temporada y tipo de día (minutos
 * desde medianoche, [inicio, fin)). Pensado para clientes que evalúan muchos
 * días sin hacer una consulta por día (por ejemplo, un motor de facturación).
 */
export function consultarCalendario(args: Args) {
  const anio = entero(args.anio);
  if (anio === null) return { error: "Falta anio." };
  if (!anioValido(anio)) return { error: "El año debe ser un número de cuatro dígitos razonable." };

  const ubic = resolverRegion(args);
  if ("error" in ubic) return ubic;

  const zona = zonaDeRegion(ubic.region);
  if (!zona) return { error: `Región desconocida: ${ubic.region}.`, regiones: listarRegiones() };

  const verano = zona.temporadas["verano"];
  const invierno = zona.temporadas["invierno"];
  if (!verano?.regla || !invierno) return { error: "No se pudo determinar la temporada para esa zona." };

  return {
    region: ubic.region,
    ...describirHorario(ubic.region),
    ...datosMunicipio(ubic),
    zona: zona.zona,
    anio,
    verano: {
      inicio: iso(resolver(verano.regla.inicio, anio)),
      fin: iso(resolver(verano.regla.fin, anio)),
      vigencia: verano.vigencia,
    },
    invierno: { vigencia: invierno.vigencia },
    festivos: festivos(anio),
    dias: { verano: verano.dias, invierno: invierno.dias },
    ...(ubic.regiones.length > 1
      ? { nota_region: `El municipio tiene más de una división (${ubic.regiones.join(", ")}); ` +
          "se devuelve la primera. Confírmala en el recibo." }
      : {}),
    nota:
      "verano.inicio y verano.fin son inclusivos; el resto del año es invierno. " +
      "Los festivos (art. 74 LFT salvo fracción IX) se tratan como domingo. " +
      "Las franjas van en minutos desde medianoche, [inicio, fin).",
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
    sistema_horario: describirHorario(r).sistema_horario,
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
