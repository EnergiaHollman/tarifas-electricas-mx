import type { resumenRegiones } from "./consultas";
import { AVISO } from "./datos";

type Resumen = ReturnType<typeof resumenRegiones>;

/** Los ejemplos: una sola lista que alimenta la portada y el llms.txt. */
function ejemplos(o: string) {
  return [
    { url: `${o}/v1/tarifa?estado=SONORA&municipio=NAVOJOA&anio=2026&mes=3`,
      que: "Cargos por estado y municipio" },
    { url: `${o}/v1/tarifa?region=NOROESTE&anio=2026&mes=3`,
      que: "Cargos por región tarifaria, si ya se conoce" },
    { url: `${o}/v1/horarios?region=NOROESTE&fecha=2026-08-15&hora=20:30`,
      que: "Temporada, tipo de día y franjas base/intermedia/punta" },
    { url: `${o}/v1/regiones`, que: "Regiones y periodos disponibles" },
    { url: `${o}/v1/estados`, que: "Estados con catálogo cargado" },
    { url: `${o}/v1/municipios?estado=SONORA`, que: "Municipios y su región" },
    { url: `${o}/openapi.json`, que: "Especificación OpenAPI 3.1" },
  ];
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/**
 * Portada.
 *
 * Los endpoints van como enlaces reales y no como texto dentro de un bloque
 * de código: los agentes que navegan solo pueden abrir URLs que hayan visto
 * enlazadas, así que en <pre> quedaban fuera de su alcance.
 */
export function portada(origen: string, resumen: Resumen) {
  const enlaces = ejemplos(origen)
    .map((e) => `<li><a href="${esc(e.url)}"><code>${esc(e.url.replace(origen, ""))}</code></a>
    <span class="que">${e.que}</span></li>`)
    .join("\n");

  const regiones = resumen.regiones.length
    ? resumen.regiones
        .map((r) => `<li><code>${r.region}</code> <span class="que">${r.periodos} periodo(s)</span></li>`)
        .join("")
    : "<li>Todavía sin datos capturados.</li>";

  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>API de tarifas eléctricas CFE</title>
<meta name="description" content="Cargos y horarios de las tarifas que CFE publica en México, consultables por programa. Servicio no oficial.">
<link rel="alternate" type="text/markdown" href="${origen}/llms.txt" title="Resumen para agentes">
<style>
  :root { color-scheme: light dark; --tinta:#16181d; --papel:#fbfaf7; --suave:#6b7280; --linea:#e3e1dc; --acento:#1f6f5c; }
  @media (prefers-color-scheme: dark) {
    :root { --tinta:#e9e8e4; --papel:#15171a; --suave:#9aa0a6; --linea:#2c3036; --acento:#6fd3b4; }
  }
  * { box-sizing:border-box }
  body { margin:0; padding:2.5rem 1.25rem 4rem; background:var(--papel); color:var(--tinta);
         font:16px/1.65 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  main { max-width:48rem; margin:0 auto }
  h1 { font-size:1.6rem; margin:0 0 .25rem; letter-spacing:-.01em }
  h2 { font-size:1.05rem; margin:2.25rem 0 .6rem; letter-spacing:-.005em }
  p.sub { color:var(--suave); margin:0 0 2rem }
  code { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.875em;
         background:color-mix(in srgb, var(--tinta) 6%, transparent); padding:.1em .35em; border-radius:4px }
  a { color:var(--acento) }
  ul { padding-left:0; list-style:none }
  ul li { margin:.45rem 0; overflow-wrap:anywhere }
  .que { color:var(--suave); font-size:.86rem; display:block }
  .aviso { border-left:3px solid var(--acento); padding:.6rem 0 .6rem 1rem; color:var(--suave); font-size:.9rem }
  footer { margin-top:3rem; padding-top:1.25rem; border-top:1px solid var(--linea); color:var(--suave); font-size:.85rem }
</style>
</head>
<body><main>
<h1>API de tarifas eléctricas CFE</h1>
<p class="sub">Cargos y horarios de las tarifas publicadas por CFE, consultables por programa.</p>

<div class="aviso">${AVISO}</div>

<h2>Consultas</h2>
<ul>
${enlaces}
</ul>

<h2>Para agentes de IA</h2>
<p>Servidor MCP en <code>${origen}/mcp</code>, con las herramientas
<code>consultar_tarifa</code>, <code>consultar_horarios</code> y
<code>listar_regiones</code>. Agrégalo como conector remoto.</p>
<p>Sin conector, cualquier agente con navegación puede usar los enlaces de
arriba. Hay un resumen en <a href="${origen}/llms.txt"><code>/llms.txt</code></a>.</p>

<h2>Cobertura</h2>
<ul>${regiones}</ul>
<p class="sub">${resumen.total_registros} registro(s). Última actualización:
${resumen.tarifas_actualizadas ?? "sin datos"}.${resumen.catalogo_parcial ? " Catálogo de municipios incompleto." : ""}</p>

<footer>Datos públicos. Código abierto, licencia MIT. Sin afiliación con la Comisión Federal de Electricidad.</footer>
</main></body></html>`;
}

/**
 * /llms.txt: resumen en Markdown pensado para que un agente entienda la API
 * de una lectura, sin tener que deducirla del HTML ni del OpenAPI.
 */
export function llmsTxt(origen: string, resumen: Resumen) {
  const lista = ejemplos(origen).map((e) => `- [${e.que}](${e.url})`).join("\n");
  const regiones = resumen.regiones.map((r) => r.region).join(", ") || "ninguna todavía";

  return `# API de tarifas eléctricas CFE

> Cargos y horarios de las tarifas que la Comisión Federal de Electricidad
> publica en México. Se consulta por estado y municipio, o por región
> tarifaria, más año y mes. Servicio no oficial, sin afiliación con CFE.

${AVISO}

## Cómo se consulta

Todo son GET sin autenticación y devuelven JSON.

${lista}

Parámetros de \`/v1/tarifa\`: \`estado\` y \`municipio\`, o bien \`region\`;
más \`anio\` (número) y \`mes\` (1 a 12). Opcional \`tarifa\`, por omisión
\`GDMTH\`.

Parámetros de \`/v1/horarios\`: la misma ubicación, más \`fecha\` en formato
AAAA-MM-DD y opcionalmente \`hora\` en HH:MM.

## Qué devuelve

Los cargos vienen en \`cargos\`: \`fijo\` en $/mes, \`base\`, \`intermedia\` y
\`punta\` en $/kWh, \`distribucion\` y \`capacidad\` en $/kW. Cada registro
trae \`fuente\` y \`fecha_captura\`.

\`/v1/horarios\` resuelve la temporada vigente (verano o invierno), el tipo de
día (hábil, sábado, o domingo y festivo) y las franjas horarias. Los días de
descanso obligatorio del artículo 74 de la LFT, salvo la fracción IX, se
tratan como domingo.

## Advertencias

Un municipio puede pertenecer a más de una división tarifaria. En ese caso la
respuesta trae \`regiones\` y \`resultados\` con una entrada por división, y
cuál aplica depende del punto de suministro: solo el recibo lo dice.

Un periodo no capturado devuelve 404 con \`periodos_disponibles\`.

## Para agentes con soporte MCP

Servidor MCP en ${origen}/mcp (JSON-RPC sobre POST). Herramientas:
\`consultar_tarifa\`, \`consultar_horarios\`, \`listar_regiones\`.

## Cobertura actual

Regiones: ${regiones}.
Registros: ${resumen.total_registros}.
Actualizado: ${resumen.tarifas_actualizadas ?? "sin datos"}.
`;
}
