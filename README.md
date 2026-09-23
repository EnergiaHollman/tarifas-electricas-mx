# API de tarifas eléctricas CFE

Consulta programática de los cargos y horarios que la Comisión Federal de
Electricidad publica para sus tarifas en México. Das estado, municipio y mes;
regresa los cargos y las franjas de base, intermedia y punta.

**Este no es un servicio oficial de CFE ni tiene afiliación con ella.** Los
datos se capturan del portal público y se republican tal cual, con la fecha en
que se capturó cada registro. La fuente autoritativa sigue siendo el portal de
CFE.

## Cómo está armado

El portal de CFE no tiene API: es ASP.NET WebForms, cada desplegable dispara un
postback completo. En vez de exponer eso al tráfico, el proyecto lo separa en
dos mitades que no se hablan en tiempo real:

```
scraper/   Python. Corre una vez al mes. Habla con CFE.
  ↓
data/      Tres JSON versionados en git. El producto durable.
  ↓
worker/    TypeScript. La API. Solo lee los JSON, nunca toca CFE.
```

El Worker se despliega en la red de Cloudflare, igual que un proyecto de
Vercel: no corre en tu equipo y no hay máquina que mantener encendida. Los
datos van empaquetados dentro del Worker al desplegar, así que tampoco hay
base de datos ni caché que invalidar. Un mes cerrado nunca
cambia, así que actualizar datos es simplemente volver a desplegar.

Consecuencia práctica: la API responde en milisegundos y sigue funcionando
aunque el portal de CFE esté caído.

## Puesta en marcha

> Para la versión detallada, con cada clic de GitHub y Cloudflare, los
> tiempos esperados y qué hacer si algo falla, ve **[GUIA_INSTALACION.md](GUIA_INSTALACION.md)**.
> Lo de abajo es el resumen.

Necesitas Python 3.10+, Node 18+, una cuenta de GitHub y una de Cloudflare.
Las dos son gratuitas y el plan gratis de Cloudflare (100,000 peticiones
diarias) es de sobra para esto.

### 1. Clona y prueba que todo corre

```bash
pip install -r scraper/requirements.txt
cd scraper && python3 test_parser.py
```

Debe decir que todas las pruebas pasaron. Prueban el parser contra el HTML
real guardado en `scraper/muestra/`.

```bash
cd ../worker && npm install && node pruebas/prueba_api.mjs
```

Prueba la API completa con los datos semilla, sin desplegar nada.

### 2. Haz el primer backfill

Puedes hacerlo de dos maneras. **Ninguna deja tu computadora como servidor:**
el backfill es una captura de datos que se corre una vez y ya.

**Opción A: desde GitHub (recomendada).** Sube el repositorio, configura el
secret del paso 4 y lanza Actions → *Backfill (manual)* → Run workflow. Corre
en los servidores de GitHub, hace commit de los datos y despliega solo. Tu
equipo no participa.

**Opción B: local**, útil la primera vez para ver los errores de cerca:

```bash
cd scraper
python3 construir_catalogo.py --estados SONORA,SINALOA
python3 actualizar_tarifas.py --regiones NOROESTE --desde 2026
```

`construir_catalogo.py` hace un postback por municipio, así que tarda. Guarda
después de cada estado y es reanudable: si se corta, vuelve a correrlo y sigue
donde quedó. El país completo (sin `--estados`) son unos 2,400 municipios,
cerca de una hora.

**Antes de lanzar el histórico completo, valida contra un recibo real.** Toma
un recibo de CFE de un mes cualquiera y compara los seis cargos. Si cuadran,
el pipeline está bien y puedes pedir todo:

```bash
python3 actualizar_tarifas.py --desde 2017
```

CFE tiene histórico desde 2017.

### 3. Despliega la API

```bash
cd worker
npx wrangler login          # abre el navegador y autoriza
npx wrangler deploy
```

Te devuelve una URL tipo `https://tarifas-electricas-mx.contacto-746.workers.dev`.
Pruébala:

```bash
curl "https://TU-URL/v1/tarifa?estado=SONORA&municipio=NAVOJOA&anio=2026&mes=3"
```

Si quieres dominio propio, en el panel de Cloudflare: Workers → tu worker →
Settings → Domains & Routes. No hay que tocar código.

### 4. Deja el cron corriendo

Sube el repositorio a GitHub. Luego:

1. En Cloudflare, My Profile → API Tokens → Create Token → plantilla
   **Edit Cloudflare Workers**. Copia el token.
2. En GitHub, Settings → Secrets and variables → Actions → New repository
   secret, con nombre `CLOUDFLARE_API_TOKEN`.
3. Pestaña Actions → *Actualizar tarifas* → **Run workflow**, para probarlo
   ahora en vez de esperar al día 3.

A partir de ahí, cada mes el Action captura lo que falte, hace commit y
redespliega. Si CFE rediseña la página, el Action falla en el paso de pruebas
del parser **antes** de tocar los datos, y te llega el correo de GitHub. Ese
es tu sistema de alertas.

### 5. Conéctalo a un agente

En Claude: Settings → Connectors → Add custom connector, con la URL
`https://TU-URL/mcp`. Quedan disponibles tres herramientas y ya puedes
preguntar en lenguaje natural por cargos y horarios.

Cualquier otro cliente con soporte MCP funciona igual apuntando a esa URL. Ver
la sección **Servidor MCP** más abajo para el detalle del protocolo, cómo
probarlo con MCP Inspector y cómo conectarlo a ChatGPT específicamente.

## Endpoints

```
GET /v1/tarifa?estado=SONORA&municipio=NAVOJOA&anio=2026&mes=3
GET /v1/tarifa?region=NOROESTE&anio=2026&mes=3&tarifa=GDMTH
GET /v1/horarios?region=NOROESTE&fecha=2026-08-15&hora=20:30
GET /v1/regiones
GET /v1/estados
GET /v1/municipios?estado=SONORA
GET /v1/salud
GET /openapi.json
GET /llms.txt
POST /mcp
```

La portada publica los endpoints como enlaces reales, no como texto en un
bloque de código: los agentes que navegan solo abren URLs que hayan visto
enlazadas. `/llms.txt` es un resumen en Markdown de la API, pensado para que
un agente la entienda de una lectura sin deducirla del HTML.

`/v1/horarios` no solo devuelve las franjas: resuelve la temporada vigente, el
tipo de día y, si le pasas una hora, en qué periodo cae. Los días de descanso
obligatorio del artículo 74 de la LFT (salvo la fracción IX) se tratan como
domingo, como manda la tarifa.

Ejemplo de respuesta:

```json
{
  "tarifa": "GDMTH",
  "region": "NOROESTE",
  "estado": "SONORA",
  "municipio": "NAVOJOA",
  "anio": 2026, "mes": 3,
  "periodo_cfe": "MAR-26",
  "cargos": {
    "fijo": 197.77, "base": 0.9715, "intermedia": 1.5573,
    "punta": 1.7262, "distribucion": 90.85, "capacidad": 392.66
  },
  "unidades": { "fijo": "$/mes", "base": "$/kWh", "distribucion": "$/kW" },
  "fuente": "https://app.cfe.mx/...",
  "fecha_captura": "2026-09-17T21:43:00+00:00"
}
```

## Servidor MCP

`POST /mcp` habla [Model Context Protocol](https://modelcontextprotocol.io)
sobre el transporte **Streamable HTTP** vigente (JSON-RPC 2.0, un objeto por
petición). No es un servicio oficial de CFE: sirve los datos que ya están
capturados en este repositorio, igual que el REST.

**Sin estado, a propósito.** Cada llamada a una herramienta es independiente;
no hay nada que una sesión resolviera aquí. Este servidor nunca emite
`Mcp-Session-Id` — la especificación permite explícitamente no hacerlo
("a server ... **MAY** assign a session ID"), así que omitirlo es una opción
válida, no una carencia. Por el mismo motivo, `GET /mcp` y `DELETE /mcp`
responden `405`: no hay stream que abrir ni sesión que terminar, y la propia
especificación autoriza responder así en ambos casos.

**`MCP-Protocol-Version`: opción A, no B.** Había dos caminos razonables:

- **A.** Mantenerse sin estado y ser tolerante: aceptar que el header falte
  (la propia especificación dice que, sin él, hay que asumir `2025-03-26` por
  retrocompatibilidad) y solo rechazar cuando el header SÍ viene con un valor
  que este servidor no reconoce en absoluto.
- **B.** Implementar sesiones MCP de verdad, para poder exigir el header en
  todas las llamadas posteriores a `initialize`.

**Se eligió A.** No hay ningún estado por correlacionar entre llamadas -cada
`tools/call` es autosuficiente-, así que una sesión no resolvería ningún
problema real aquí; solo añadiría infraestructura (KV o Durable Objects para
guardar sesiones, lógica de expiración) a cambio de nada. B se descartó
explícitamente por parecer "más completo", no porque A fuera insuficiente.

**Versión de protocolo.** Se negocian `2025-06-18` y `2025-11-25` (a efectos
de transporte son la misma cosa). Existe una revisión candidata `2026-07-28`
que elimina el handshake `initialize` y las sesiones por completo, pero al
escribir esto sigue marcada como *release candidate* en la especificación
oficial y ningún cliente mayor (Claude, ChatGPT, MCP Inspector) la habla de
forma consistente todavía. Se optó por no adoptarla; es una decisión
documentada, no un descuido. La negociación nunca miente: si el cliente pide
una versión que no se reconoce, la respuesta de `initialize` trae la versión
que el servidor realmente ofrece en `result.protocolVersion`, nunca la que
pidió el cliente disfrazada de aceptada — así el cliente puede decidir con
información correcta si quiere continuar o no.

**Sin el SDK oficial de MCP, a propósito.** El `@modelcontextprotocol/sdk`
está pensado para Node/Express o stdio; adaptarlo al runtime de Cloudflare
Workers (que solo conoce `fetch`/`Request`/`Response`, sin streams de Node)
exige una capa de compatibilidad no trivial a cambio de un beneficio marginal
frente a una implementación manual de JSON-RPC de unas 250 líneas, que ya
cubre el protocolo correctamente. Prioriza bajo mantenimiento y cero
dependencias nuevas sobre usar el SDK porque existe.

### Herramientas

| Herramienta | Para qué |
|---|---|
| `consultar_tarifa` | Cargos de una tarifa (fijo, base, intermedia, punta, distribución, capacidad) para una ubicación y un mes |
| `consultar_horarios` | Temporada, tipo de día y franjas base/intermedia/punta para una fecha; en qué periodo cae una hora concreta |
| `listar_regiones` | Regiones tarifarias conocidas y cobertura de datos disponible |

Las tres son de solo lectura sobre el JSON estático empaquetado en el Worker
(sin red, sin CFE en vivo), y así lo declaran sus anotaciones:
`readOnlyHint: true`, `destructiveHint: false`, `openWorldHint: false` (el
universo de respuestas es el dataset ya capturado, no un sistema externo
impredecible). No declaran `idempotentHint`: la propia especificación dice
que esa anotación solo es significativa para herramientas que no son de solo
lectura, así que declararla aquí sería una anotación que no corresponde.

Las descripciones de cada herramienta están escritas para que un agente
decida sin ambigüedad: cuándo usar `region` directamente frente a
`estado`+`municipio`, que `mes` es un entero de 1 a 12 (no el nombre del
mes), que `fecha` va en ISO `AAAA-MM-DD` y `hora` en 24 horas `HH:MM`, y que
`GDMTH` es la tarifa por omisión porque es la única con datos capturados hoy.

Los tres esquemas declaran `additionalProperties: false`, y no es solo
decorativo: una propiedad que el esquema no reconoce se rechaza de verdad
como error de protocolo (`-32602`), no se ignora en silencio ni se trata como
un dato de negocio inválido.

### Errores: protocolo vs. resultado, y lo inesperado

Siguiendo la distinción que hace la propia especificación:

- **Error de protocolo** (JSON-RPC `error`, sin `isError`): la petición en sí
  está mal formada — herramienta desconocida, método inexistente, falta el
  nombre en `tools/call`, JSON roto, o una propiedad que el esquema no
  declara. `Unknown tool: X` con código `-32602` es, literalmente, el ejemplo
  que trae la especificación para ese caso.
- **Error de ejecución** (`isError: true` dentro de un resultado `200`): la
  llamada era válida pero el *dato* no aplica — mes 13, municipio que no está
  en el catálogo, fecha con formato roto, o un periodo que no está capturado
  todavía. La herramienta sí corrió; lo que falló es la consulta, y la
  respuesta siempre dice por qué (por ejemplo, `periodos_disponibles` con lo
  que sí existe).
- **Error interno inesperado** (`-32603 Internal error`): red de seguridad
  para cualquier excepción que no debería ocurrir -las funciones de
  `consultas.ts` están escritas para devolver `{error: ...}` en vez de
  lanzar-, pero si algo revienta de todos modos, se convierte en un error
  JSON-RPC de verdad en lugar de tumbar la petición con un 500 sin envoltura.

### Ejemplo de sesión completa

```
POST /mcp   {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}
  -> {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","serverInfo":{...},...}}

POST /mcp   {"jsonrpc":"2.0","method":"notifications/initialized"}
  -> 202 Accepted, sin cuerpo

POST /mcp   {"jsonrpc":"2.0","id":2,"method":"tools/list"}
  -> {"jsonrpc":"2.0","id":2,"result":{"tools":[consultar_tarifa, consultar_horarios, listar_regiones]}}

POST /mcp   {"jsonrpc":"2.0","id":3,"method":"tools/call",
             "params":{"name":"consultar_tarifa",
                       "arguments":{"estado":"SONORA","municipio":"NAVOJOA","anio":2026,"mes":3}}}
  -> {"jsonrpc":"2.0","id":3,"result":{"structuredContent":{"region":"NOROESTE","cargos":{...}},...}}
```

Una pregunta como *"Obtén la tarifa GDMTH de Navojoa, Sonora, para marzo de
2026"* se resuelve enteramente con esa última llamada: el agente ve en la
descripción de `consultar_tarifa` que puede dar `estado`+`municipio` sin
saber la región, y la herramienta resuelve sola SONORA+NAVOJOA → NOROESTE.

### Probar contra el despliegue real, no solo en local

`prueba_api.mjs` y `prueba_mcp.mjs` corren contra una copia del Worker
empaquetada con esbuild en memoria — rápido y sin red, pero no es lo mismo
que el servidor de verdad respondiendo desde el borde de Cloudflare.
`prueba_mcp_remoto.mjs` sí le pega a la URL real:

```bash
cd worker
MCP_URL=https://tarifas-electricas-mx.contacto-746.workers.dev/mcp node pruebas/prueba_mcp_remoto.mjs
# o, para usar la URL pública del proyecto por omisión:
npm run test:remote
```

Corre la cadena completa (`initialize` → `notifications/initialized` →
`tools/list` → las tres herramientas), incluida la resolución
`SONORA + NAVOJOA -> NOROESTE` contra los datos reales ya desplegados, y
compara los cargos de marzo de 2026 contra la referencia de este README. Si
no hay salida a Internet, lo dice explícitamente y termina con código de
salida `2` (no `1`), para no confundir "no hay red" con "el servidor está
mal" en un pipeline de CI.

### Probarlo con MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

En la interfaz que abre:

1. **Transport Type**: `Streamable HTTP`
2. **URL**: `https://TU-URL/mcp`
3. **Connect**
4. Pestaña **Tools** → **List Tools**: deben aparecer las tres herramientas
   con sus esquemas
5. Selecciona `consultar_tarifa`, llena `estado=SONORA`, `municipio=NAVOJOA`,
   `anio=2026`, `mes=3` → **Run Tool**

Si el Inspector muestra el resultado con `region: "NOROESTE"` y los seis
cargos, el servidor está funcionando de punta a punta.

### Conectarlo a ChatGPT

ChatGPT solo admite servidores MCP **remotos por HTTPS** (no hay stdio ni
servidor local salvo con el Secure MCP Tunnel de empresa) y solo consume
`tools` de un servidor MCP — ignora `resources`, `prompts`, `sampling` y
`elicitation`, así que un servidor solo-herramientas como este es exactamente
lo que espera.

1. En ChatGPT: **Settings** → **Apps & Connectors** (o **Connectors**, según
   el plan) → activa **Developer mode** si hace falta
2. **Create** / **Add custom connector**
3. **Name**: algo descriptivo, p. ej. "Tarifas eléctricas CFE"
4. **URL del servidor**: `https://TU-URL/mcp` — el sufijo `/mcp` es
   obligatorio, es el error de configuración más común
5. **Autenticación**: ninguna. Este servidor no pide credenciales porque no
   hay datos privados ni acciones sobre cuentas; los datos son públicos
6. Guarda, abre una conversación, activa el conector desde el compositor y
   pregunta algo como *"¿cuál fue la tarifa GDMTH de Navojoa, Sonora, en
   marzo de 2026?"*

### Limitaciones conocidas

- No implementa las herramientas `search`/`fetch` que pide el patrón de
  *deep research* / *company knowledge* de OpenAI. Ese es un contrato
  distinto (búsqueda libre + recuperación de documentos) al de consulta
  directa por parámetros que tienen `consultar_tarifa` y `consultar_horarios`;
  añadirlo sería un cambio de diseño, no un ajuste de compatibilidad.
- No declara `outputSchema` por herramienta. Es opcional en la especificación
  y añadirlo bien (mantenerlo sincronizado con las formas de respuesta, que
  varían cuando un municipio tiene más de una división) es más compromiso de
  mantenimiento del que se justifica hoy.
- No hay autenticación ni límite de uso propio más allá de lo que ya impone
  Cloudflare. No hace falta: los datos son públicos y de solo lectura.

## Agregar otras tarifas

El portal sirve GDMTO, PDBT, DIST y las domésticas con exactamente la misma
mecánica; solo cambia la URL de la página. En `scraper/cfe.py`, el diccionario
`PAGINAS` ya tiene tres entradas: agrega la que quieras y córrelo con
`--tarifa GDMTO`. El modelo de datos ya lleva el campo `tarifa` en la clave,
así que no hay que migrar nada.

Las URL de GDMTO y PDBT que vienen precargadas están **sin verificar**;
confírmalas en el portal antes de usarlas.

## Cuando CFE cambie la página

Todo lo que depende del HTML de CFE vive en `scraper/parser.py`. El
procedimiento es siempre el mismo:

1. Abre la página en el navegador, Ctrl+S, guarda sobre
   `scraper/muestra/GranDemandaMTH.html`.
2. `cd scraper && python3 test_parser.py` para ver qué se rompió.
3. Arregla `parser.py` hasta que pase.

Nada más del proyecto necesita cambios: ni la API, ni el modelo de datos, ni
los despliegues anteriores.

## Estructura

| Ruta | Qué es |
|---|---|
| `scraper/parser.py` | Parseo del HTML. Lo único frágil ante rediseños de CFE |
| `scraper/preparar_tls.py` | Completa la cadena de certificados que CFE no manda |
| `scraper/cfe.py` | Cliente WebForms: sesión y cadena de postbacks |
| `scraper/construir_catalogo.py` | Municipio → región tarifaria. Se corre una vez |
| `scraper/actualizar_tarifas.py` | Captura de cargos y horarios. Lo que corre el cron |
| `scraper/sembrar_desde_muestra.py` | Genera `data/` desde la muestra, sin red |
| `scraper/test_parser.py` | Pruebas del parser contra HTML real |
| `scraper/test_catalogo.py` | Pruebas de etiquetas compuestas y representantes |
| `scraper/test_cfe_session.py` | Prueba del guardián contra sesiones con la región contaminada |
| `.github/workflows/backfill.yml` | Captura histórica a demanda, desde GitHub |
| `.github/workflows/actualizar.yml` | Captura mensual automática |
| `data/catalogo.json` | Estado → municipio → región |
| `data/tarifas.json` | Cargos por tarifa, región y mes |
| `data/horarios.json` | Franjas por zona y temporada, con reglas de vigencia |
| `worker/src/calendario.ts` | Temporada, festivos, tipo de día, periodo tarifario |
| `worker/src/consultas.ts` | Lógica compartida entre REST y MCP |
| `worker/src/mcp.ts` | Servidor MCP: Streamable HTTP, JSON-RPC 2.0 |
| `worker/pruebas/_entorno.mjs` | Bootstrap compartido (empaqueta el Worker con esbuild) |
| `worker/pruebas/prueba_api.mjs` | Pruebas de REST, portada, llms.txt, robots.txt, CORS |
| `worker/pruebas/prueba_mcp.mjs` | Pruebas del servidor MCP: initialize, tools/list, las tres herramientas, errores |
| `worker/pruebas/prueba_mcp_remoto.mjs` | Prueba end-to-end contra el despliegue real (`MCP_URL`) |

## Notas de captura

- En el año en curso, CFE solo lista los meses ya publicados; el scraper lee
  el desplegable en vez de asumir doce.
- Los cargos dependen de la región tarifaria, no del municipio. El scraper usa
  un municipio representativo por región: ocho consultas por mes en lugar de
  2,400.
- Un municipio puede tener **más de una división tarifaria**. Ocurre de dos
  formas: el desplegable ofrece varias opciones (Toluca), o una sola opción
  cuyo texto abarca varias ("Bajío y Golfo Centro"). En ambos casos la página
  devuelve una tabla por división y la API las devuelve todas, porque cuál
  aplica depende del punto de suministro y eso solo lo dice el recibo.
- El encabezado de la página de resultados **no es de fiar**: para Baja
  California Sur imprime "Baja California". Cuando la respuesta trae una sola
  tabla, la división es la que se seleccionó en el desplegable; los encabezados
  solo se usan para desglosar las etiquetas compuestas, que devuelven varias.
- **El control de mes cambia de nombre según el año elegido.** Para el año en
  curso la página usa `Fecha2$ddMes`; para cualquier año pasado, ese control
  no se renderiza en absoluto y aparece uno distinto en su lugar,
  `MesVerano3$ddMesConsulta`. No son variantes del mismo campo: son dos
  controles ASP.NET diferentes. `parser.control_mes()` detecta cuál está
  presente en cada respuesta y el resto del scraper lo usa de forma
  transparente. Este fue el motivo real por el que el histórico nunca se
  capturaba: se buscaba siempre el control del año en curso.
- Las etiquetas compuestas **no se pueden partir por texto**: CFE elide el
  prefijo compartido, así que "Valle de México Centro y Sur" son Centro y Sur
  del Valle de México, no una división llamada "Sur". El scraper consulta una
  vez cada etiqueta, lee los encabezados reales que devuelve la página y
  guarda la equivalencia en `catalogo.json`, bajo `expansiones`. Esas
  equivalencias se validan al leerlas: una de un solo elemento tiene que ser
  la etiqueta misma, así que las heredadas de versiones con criterios
  distintos se detectan y se vuelven a resolver solas. `--reresolver` fuerza
  rehacerlas todas.
- **Incidente real, ya corregido (segunda parte):** el guardián de nombre
  visible de arriba no bastó. En una corrida real, `BAJA CALIFORNIA` -una
  etiqueta de una sola región, ya confirmada así por `resolver_etiquetas`-
  devolvió en cierto tramo **dos tablas** en la respuesta (una ajena, de
  "Valle de México Sur"), y como nada comparaba el número de tablas contra
  lo que ya se sabía, el código se creyó las dos. Ahora `divisiones_de`
  recibe `regiones_esperadas` -la lista ya resuelta antes, en
  `resolver_etiquetas`- y si el número de tablas no coincide exactamente,
  devuelve `None`: no se guarda ninguna de las tablas de ese mes, y se cuenta
  como sospechoso. La asimetría importa: de más tablas que las esperadas
  siempre es sospechoso; de menos, en teoría podría ser una etiqueta
  compuesta con publicación parcial, aunque no hay evidencia de que eso
  ocurra -CFE publica todo o nada, según lo visto en varios backfills
  completos-, así que por ahora se trata igual de estricto en ambos casos.
  Cubierto por `test_catalogo.py`, que reproduce el escenario exacto (una
  etiqueta pura recibiendo una tabla de sobra) y confirma que se rechaza.
- **Resuelto con datos reales, tras un backfill real:** un mismo mes
  (febrero de 2018) salió "sospechoso" en las 17 regiones a la vez, siempre
  con dos tablas del mismo nombre de región. No era corrupción: es que CFE
  **republicó** ese mes. La página, cuando eso pasa, muestra dos cuotas para
  el mismo periodo, cada una precedida por su propio texto explicativo -
  confirmado contra el sitio real por quien usa este proyecto-: "2.1.1 ...
  facturados en el mes de X, con consumos dentro del propio mes" (la
  provisional) y "2.1.2 ... facturados en el mes de Y, con consumos dentro
  del mes de X" (la definitiva, la que casi todo el mundo factura de verdad,
  porque el recibo llega el mes siguiente al consumo, no el mismo mes).
  `parser._clasificar_facturacion()` detecta cuál tabla es cuál leyendo ese
  texto, y `actualizar_tarifas.tabla_definitiva()` prefiere automáticamente
  la marcada "mes_siguiente" -deja una nota explícita en el registro-; solo
  si el patrón no aplica con claridad (ninguna tabla marcada así, o más de
  una) se sigue dejando como sospechoso de verdad. Se verificó que este caso
  de dos tablas **no** afecta al resto del histórico: las muestras usadas
  desde el principio del proyecto (marzo de 2026, mayo de 2019) traen una
  sola tabla cada una, sin este patrón -CFE solo lo usa cuando corrige un
  mes ya publicado.
- **Incidente en el propio automatismo, ya corregido:** cuando el guardián de
  arriba detecta un sospechoso, `actualizar_tarifas.py` sale con código de
  error a propósito -para que alguien lo note-, pero el paso "Confirmar
  cambios" de los workflows no tenía `if: always()`. Un solo mes sospechoso
  en una corrida de casi dos horas hacía que GitHub Actions saltara por
  completo el commit y el push, perdiendo TODOS los datos buenos que sí se
  habían capturado bien, no solo el mes problemático. Pasó de verdad en un
  backfill real: 1768 registros capturados correctamente, descartados porque
  el paso de guardarlos nunca corrió. Ahora "Confirmar cambios", "Probar la
  API" y "Desplegar" llevan `always()`: se comitea y despliega lo que sí se
  capturó bien, y el job sigue marcándose en rojo (para que se note que hay
  sospechosos que revisar), pero sin tirar el trabajo bueno a la basura.
- **Incidente real, ya corregido:** `poner_region` comparaba solo el *id*
  numérico de la división, nunca el nombre visible. En un backfill largo, en
  algún punto la página quedó mostrando "Valle de México Sur" mientras el
  código pedía "Baja California" con un id que coincidía por casualidad;
  como el id ya coincidía, el código viejo no volvía a seleccionar nada y
  guardó varios meses de 2023-2025 bajo la región equivocada. Ahora
  `poner_region` y `consultar()` verifican también el **nombre visible**, no
  solo el id, y revientan con un error claro (`ErrorCFE`, contado como
  "sospechoso" en el resumen final) en vez de guardar en silencio un dato mal
  etiquetado. Cubierto por `scraper/test_cfe_session.py`, que reproduce el
  escenario exacto con HTML sintético. Si `actualizar_tarifas.py` reporta
  algún "sospechoso", la corrida termina con código de salida distinto de
  cero a propósito: hay que mirar el log, no solo relanzar. (Se sospechó que
  una cookie de sesión reutilizada tenía algo que ver, y por eso el proyecto
  llegó a soportar `CFE_COOKIES`; se probó sin cookie después de este
  arreglo y el histórico se captura igual, así que ya no se usa ni hace
  falta configurarla.) Importante: `--rehacer` sobreescribe un registro solo
  si el reintento tiene éxito; si el guardián lo detiene de nuevo, el dato
  viejo (contaminado o no) se queda tal cual. Para partir de cero de verdad
  -y no depender de que cada reintento salga bien- existe `--limpiar-todo`,
  que vacía todos los registros de `tarifas.json` antes de capturar. Es
  seguro: el archivo está versionado en git, así que nada se pierde de
  verdad.
- El scraper nunca reescribe un registro ya capturado salvo con `--rehacer`.
  Si CFE corrigiera un mes cerrado, quieres enterarte, no que se sobrescriba
  en silencio.
- Hay una pausa de 1.5 s entre peticiones y un User-Agent identificable.

## Licencia

MIT. Los datos son información pública publicada por CFE.
