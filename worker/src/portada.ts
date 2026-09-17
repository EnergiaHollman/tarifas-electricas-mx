import { AVISO } from "./datos";

export function portada(origen: string, resumen: ReturnType<typeof import("./consultas").resumenRegiones>) {
  const regiones = resumen.regiones
    .map((r) => `<li><code>${r.region}</code> — ${r.periodos} periodo(s) capturado(s)</li>`)
    .join("");
  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>API de tarifas eléctricas CFE</title>
<style>
  :root { color-scheme: light dark; --tinta:#16181d; --papel:#fbfaf7; --suave:#6b7280; --linea:#e3e1dc; --acento:#1f6f5c; }
  @media (prefers-color-scheme: dark) {
    :root { --tinta:#e9e8e4; --papel:#15171a; --suave:#9aa0a6; --linea:#2c3036; --acento:#6fd3b4; }
  }
  * { box-sizing:border-box }
  body { margin:0; padding:2.5rem 1.25rem 4rem; background:var(--papel); color:var(--tinta);
         font:16px/1.65 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  main { max-width:46rem; margin:0 auto }
  h1 { font-size:1.6rem; margin:0 0 .25rem; letter-spacing:-.01em }
  h2 { font-size:1.05rem; margin:2.25rem 0 .6rem; letter-spacing:-.005em }
  p.sub { color:var(--suave); margin:0 0 2rem }
  code, pre { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.875em }
  pre { background:color-mix(in srgb, var(--tinta) 5%, transparent); border:1px solid var(--linea);
        border-radius:8px; padding:.85rem 1rem; overflow-x:auto }
  a { color:var(--acento) }
  ul { padding-left:1.15rem }
  .aviso { border-left:3px solid var(--acento); padding:.6rem 0 .6rem 1rem; color:var(--suave); font-size:.9rem }
  footer { margin-top:3rem; padding-top:1.25rem; border-top:1px solid var(--linea); color:var(--suave); font-size:.85rem }
</style>
</head>
<body><main>
<h1>API de tarifas eléctricas CFE</h1>
<p class="sub">Cargos y horarios de las tarifas publicadas por CFE, consultables por programa.</p>

<div class="aviso">${AVISO}</div>

<h2>Consultas</h2>
<pre>GET ${origen}/v1/tarifa?estado=SONORA&amp;municipio=NAVOJOA&amp;anio=2026&amp;mes=3
GET ${origen}/v1/tarifa?region=NOROESTE&amp;anio=2026&amp;mes=3
GET ${origen}/v1/horarios?region=NOROESTE&amp;fecha=2026-08-15&amp;hora=20:30
GET ${origen}/v1/regiones
GET ${origen}/v1/estados
GET ${origen}/v1/municipios?estado=SONORA
GET ${origen}/openapi.json</pre>

<h2>Para agentes de IA</h2>
<p>Servidor MCP en <code>${origen}/mcp</code>. Agrégalo como conector remoto y quedan
disponibles <code>consultar_tarifa</code>, <code>consultar_horarios</code> y
<code>listar_regiones</code>.</p>

<h2>Cobertura</h2>
<ul>${regiones || "<li>Todavía sin datos capturados.</li>"}</ul>
<p class="sub">${resumen.total_registros} registro(s). Última actualización:
${resumen.tarifas_actualizadas ?? "sin datos"}.${resumen.catalogo_parcial ? " Catálogo de municipios incompleto." : ""}</p>

<footer>Datos públicos. Código abierto, licencia MIT. Sin afiliación con la Comisión Federal de Electricidad.</footer>
</main></body></html>`;
}
