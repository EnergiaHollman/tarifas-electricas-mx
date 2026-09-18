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

Cualquier otro cliente con soporte MCP funciona igual apuntando a esa URL.

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
| `.github/workflows/backfill.yml` | Captura histórica a demanda, desde GitHub |
| `.github/workflows/actualizar.yml` | Captura mensual automática |
| `data/catalogo.json` | Estado → municipio → región |
| `data/tarifas.json` | Cargos por tarifa, región y mes |
| `data/horarios.json` | Franjas por zona y temporada, con reglas de vigencia |
| `worker/src/calendario.ts` | Temporada, festivos, tipo de día, periodo tarifario |
| `worker/src/consultas.ts` | Lógica compartida entre REST y MCP |
| `worker/src/mcp.ts` | Servidor MCP por JSON-RPC |
| `worker/pruebas/prueba_api.mjs` | Pruebas de la API sin desplegar |

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
- El flujo real del sitio es **año, mes, estado, municipio, división** — en
  ese orden. El desplegable de meses se calcula a partir del año con una
  página recién cargada, antes de elegir ubicación; seleccionar el año con
  la ubicación ya puesta deja los meses vacíos. Por eso el scraper recarga la
  página al empezar cada año y sigue el orden real del formulario.
- Las etiquetas compuestas **no se pueden partir por texto**: CFE elide el
  prefijo compartido, así que "Valle de México Centro y Sur" son Centro y Sur
  del Valle de México, no una división llamada "Sur". El scraper consulta una
  vez cada etiqueta, lee los encabezados reales que devuelve la página y
  guarda la equivalencia en `catalogo.json`, bajo `expansiones`. Esas
  equivalencias se validan al leerlas: una de un solo elemento tiene que ser
  la etiqueta misma, así que las heredadas de versiones con criterios
  distintos se detectan y se vuelven a resolver solas. `--reresolver` fuerza
  rehacerlas todas.
- El scraper nunca reescribe un registro ya capturado salvo con `--rehacer`.
  Si CFE corrigiera un mes cerrado, quieres enterarte, no que se sobrescriba
  en silencio.
- Hay una pausa de 1.5 s entre peticiones y un User-Agent identificable. El
  acceso es mensual, no continuo.

## Licencia

MIT. Los datos son información pública publicada por CFE.
