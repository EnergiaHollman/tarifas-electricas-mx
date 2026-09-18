/**
 * API pública de tarifas eléctricas de CFE.
 *
 * No consulta a CFE: sirve los datos ya capturados por el scraper y
 * empaquetados en el Worker. Por eso responde en milisegundos y no se cae
 * aunque el portal de CFE esté fuera de servicio.
 */
import { consultarHorarios, consultarTarifa, resumenRegiones } from "./consultas";
import {
  AVISO,
  catalogo,
  listarEstados,
  listarMunicipios,
  tarifas,
} from "./datos";
import { manejarMcp } from "./mcp";
import { llmsTxt, portada } from "./portada";

// CORS evaluado explícitamente para lo que MCP necesita, nada más:
//   - content-type: el cliente lo manda en cada POST /mcp.
//   - mcp-protocol-version: el cliente lo manda tras el initialize, y el
//     servidor también lo devuelve en la respuesta (ver expose-headers).
//   - mcp-session-id: este servidor NUNCA lo emite (es stateless a
//     propósito), pero se sigue permitiendo en la petición: un cliente MCP
//     genérico puede mandarlo por defensa, y rechazar el preflight solo
//     porque nosotros no lo usamos rompería ese cliente sin necesidad.
//   - accept: no hace falta declararlo aquí. Es uno de los headers
//     "safelisted" del propio estándar CORS (junto con Accept-Language y
//     Content-Language), así que el navegador ya lo permite sin que un
//     servidor tenga que listarlo explícitamente.
// GET, POST, OPTIONS y DELETE están en allow-methods porque el propio router
// de /mcp responde algo a las cuatro (POST hace el trabajo real; GET y
// DELETE responden 405 explicado). Sin DELETE aquí, un cliente en navegador
// nunca llegaría a VER esa respuesta 405: el preflight lo bloquearía antes.
const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET, POST, DELETE, OPTIONS",
  "access-control-allow-headers": "content-type, mcp-session-id, mcp-protocol-version",
  // Sin exponer esto, un cliente MCP en navegador no puede LEER el header de
  // respuesta MCP-Protocol-Version que /mcp añade (CORS oculta por omisión
  // cualquier header que no sea "simple").
  "access-control-expose-headers": "mcp-protocol-version",
};

function json(datos: unknown, status = 200) {
  return new Response(JSON.stringify(datos, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=3600",
      ...CORS,
    },
  });
}

function resultado(r: Record<string, any>) {
  return json(r, "error" in r ? 404 : 200);
}

const OPENAPI = {
  openapi: "3.1.0",
  info: {
    title: "API de tarifas eléctricas CFE",
    version: "1.0.0",
    description:
      "Cargos y horarios de las tarifas que CFE publica en México. Servicio no " +
      "oficial, sin afiliación con CFE.",
  },
  paths: {
    "/v1/tarifa": {
      get: {
        summary: "Cargos de una tarifa para una ubicación y un mes",
        parameters: [
          { name: "estado", in: "query", schema: { type: "string" } },
          { name: "municipio", in: "query", schema: { type: "string" } },
          { name: "region", in: "query", schema: { type: "string" } },
          { name: "anio", in: "query", required: true, schema: { type: "integer" } },
          { name: "mes", in: "query", required: true, schema: { type: "integer" } },
          { name: "tarifa", in: "query", schema: { type: "string", default: "GDMTH" } },
        ],
        responses: { "200": { description: "Cargos" }, "404": { description: "Sin datos" } },
      },
    },
    "/v1/horarios": {
      get: {
        summary: "Temporada, tipo de día y franjas base/intermedia/punta",
        parameters: [
          { name: "region", in: "query", schema: { type: "string" } },
          { name: "estado", in: "query", schema: { type: "string" } },
          { name: "municipio", in: "query", schema: { type: "string" } },
          { name: "fecha", in: "query", required: true, schema: { type: "string", format: "date" } },
          { name: "hora", in: "query", schema: { type: "string" } },
        ],
        responses: { "200": { description: "Horarios" } },
      },
    },
    "/v1/regiones": { get: { summary: "Regiones y cobertura disponible" } },
    "/v1/estados": { get: { summary: "Estados con catálogo cargado" } },
    "/v1/municipios": {
      get: {
        summary: "Municipios de un estado y su región tarifaria",
        parameters: [{ name: "estado", in: "query", required: true, schema: { type: "string" } }],
      },
    },
  },
};

export default {
  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    const ruta = url.pathname.replace(/\/+$/, "") || "/";
    const q = (k: string) => url.searchParams.get(k) ?? undefined;

    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

    if (ruta === "/mcp") return manejarMcp(req, CORS);

    if (ruta === "/") {
      return new Response(portada(url.origin, resumenRegiones()), {
        headers: { "content-type": "text/html; charset=utf-8", ...CORS },
      });
    }

    if (ruta === "/openapi.json") return json(OPENAPI);

    // Convención llms.txt: resumen en Markdown para agentes.
    if (ruta === "/llms.txt" || ruta === "/llms-full.txt") {
      return new Response(llmsTxt(url.origin, resumenRegiones()), {
        headers: { "content-type": "text/markdown; charset=utf-8",
                   "cache-control": "public, max-age=3600", ...CORS },
      });
    }

    if (ruta === "/robots.txt") {
      return new Response(
        `User-agent: *\nAllow: /\n\nSitemap: ${url.origin}/llms.txt\n`,
        { headers: { "content-type": "text/plain; charset=utf-8", ...CORS } },
      );
    }

    if (ruta === "/v1/tarifa") {
      return resultado(
        consultarTarifa({
          estado: q("estado"),
          municipio: q("municipio"),
          region: q("region"),
          anio: q("anio"),
          mes: q("mes"),
          tarifa: q("tarifa"),
        }),
      );
    }

    if (ruta === "/v1/horarios") {
      return resultado(
        consultarHorarios({
          region: q("region"),
          estado: q("estado"),
          municipio: q("municipio"),
          fecha: q("fecha"),
          hora: q("hora"),
        }),
      );
    }

    if (ruta === "/v1/regiones") return json(resumenRegiones());

    if (ruta === "/v1/estados") {
      return json({ estados: listarEstados(), catalogo_parcial: catalogo.parcial === true, aviso: AVISO });
    }

    if (ruta === "/v1/municipios") {
      const estado = q("estado");
      if (!estado) return json({ error: "Falta el parámetro estado." }, 400);
      const m = listarMunicipios(estado);
      if (!m) return json({ error: `Estado no encontrado: ${estado}`, estados: listarEstados() }, 404);
      return json({ estado, municipios: m, aviso: AVISO });
    }

    if (ruta === "/v1/salud") {
      return json({
        ok: true,
        registros: Object.keys(tarifas.registros).length,
        actualizado: tarifas.actualizado,
        catalogo_generado: catalogo.generado,
      });
    }

    return json({ error: "Ruta no encontrada.", rutas: Object.keys(OPENAPI.paths) }, 404);
  },
};
