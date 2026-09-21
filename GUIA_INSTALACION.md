# Guía de instalación paso a paso

Tiempo total: entre 40 y 60 minutos de trabajo tuyo, más el tiempo que corran
solos los procesos de captura.

Nada de esto deja tu computadora como servidor. La API vive en la red de
Cloudflare y la captura de datos corre en los servidores de GitHub.

**Índice**

- [Fase 0 — Preparar lo que necesitas](#fase-0--preparar-lo-que-necesitas)
- [Fase 1 — Probar en local](#fase-1--probar-en-local)
- [Fase 2 — Subir a GitHub](#fase-2--subir-a-github)
- [Fase 3 — Cuenta y token de Cloudflare](#fase-3--cuenta-y-token-de-cloudflare)
- [Fase 4 — Primer deploy](#fase-4--primer-deploy)
- [Fase 5 — Backfill de prueba y validación](#fase-5--backfill-de-prueba-y-validación)
- [Fase 6 — Backfill completo](#fase-6--backfill-completo)
- [Fase 7 — Dejar el cron corriendo](#fase-7--dejar-el-cron-corriendo)
- [Fase 8 — Conectarlo a un agente](#fase-8--conectarlo-a-un-agente)
- [Fase 9 — Dominio propio (opcional)](#fase-9--dominio-propio-opcional)
- [Problemas comunes](#problemas-comunes)
- [Mantenimiento](#mantenimiento)

---

## Fase 0 — Preparar lo que necesitas

### 0.1 Cuentas

| Qué | Dónde | Costo |
|---|---|---|
| GitHub | github.com | Gratis |
| Cloudflare | dash.cloudflare.com/sign-up | Gratis |

En Cloudflare **no necesitas comprar dominio ni transferir nada.** Solo la
cuenta. El plan gratuito de Workers da 100,000 peticiones diarias.

### 0.2 Programas en tu computadora

Solo hacen falta para la Fase 1, que es opcional pero recomendada.

Comprueba qué tienes:

```bash
python3 --version     # necesitas 3.10 o mayor
node --version        # necesitas 18 o mayor
git --version
```

Si falta alguno:

- **Python**: python.org/downloads
- **Node**: nodejs.org (versión LTS)
- **Git**: git-scm.com/downloads

### 0.3 Decide el nombre del proyecto

Vas a usarlo en tres lados: el repositorio de GitHub, el nombre del Worker y
la URL pública.

**No uses "CFE" en el nombre.** Es una empresa del Estado y su nombre está
protegido; un dominio o repositorio que parezca oficial te expone sin
necesidad. Ideas neutras: `tarifas-electricas-mx`, `gdmth-api`,
`tarifas-mx`.

Para el resto de la guía supondré que elegiste **`tarifas-mx`**. Cámbialo
donde aparezca.

---

## Fase 1 — Probar en local

**Puedes saltarte esta fase** e ir directo a la 2. Pero vale la pena: en 5
minutos confirmas que todo funciona antes de meter cuentas y tokens.

### 1.1 Descomprime el proyecto

Descomprime el zip del proyecto donde guardes tus proyectos. Si quieres
renombrar la carpeta a `tarifas-mx`, hazlo ahora.

### 1.2 Prueba el parser

```bash
cd tarifas-mx/scraper
pip install -r requirements.txt
python3 test_parser.py
```

Debe terminar con:

```
Todas las pruebas pasaron.
```

Si falla aquí, algo está mal con la instalación de Python, no con el código:
las pruebas corren contra un HTML guardado, sin red.

### 1.3 Prueba la API

```bash
cd ../worker
npm install
node pruebas/prueba_api.mjs
```

Otra vez debe terminar en `Todas las pruebas pasaron.` Son 47 pruebas de la
API completa con datos reales.

> En Windows, si `python3` no existe usa `python`. Y si al instalar las
> dependencias de Python te dice que falta el módulo, invoca pip como módulo
> del intérprete: `python -m pip install -r requirements.txt`. Así te aseguras
> de instalar en el Python que realmente estás usando.

### 1.4 Levántala en tu navegador (opcional)

```bash
npx wrangler dev
```

La primera vez te va a pedir permiso para instalar wrangler; acepta. Abre
`http://localhost:8787` y vas a ver la portada. Prueba:

```
http://localhost:8787/v1/tarifa?estado=SONORA&municipio=NAVOJOA&anio=2026&mes=3
```

Debe devolver los cargos de marzo. `Ctrl+C` para detenerlo.

---

## Fase 2 — Subir a GitHub

### 2.1 Crea el repositorio

1. Entra a github.com y haz clic en **+** (arriba a la derecha) → **New repository**
2. **Repository name**: `tarifas-mx`
3. **Description**: algo como "Consulta programática de tarifas eléctricas publicadas por CFE"
4. Elige **Public**

   > **Por qué público:** en repositorios públicos los minutos de GitHub
   > Actions son ilimitados. En privados el plan gratuito da 2,000 minutos al
   > mes, y el backfill del país completo se come una buena parte. Además el
   > proyecto solo republica datos públicos.

5. **No marques** ninguna de las casillas de "Initialize this repository"
6. **Create repository**

### 2.2 Sube el código

En la carpeta del proyecto:

```bash
cd tarifas-mx
git init
git add .
git commit -m "Versión inicial"
git branch -M main
git remote add origin https://github.com/TU-USUARIO/tarifas-mx.git
git push -u origin main
```

Cambia `TU-USUARIO` por el tuyo. Si te pide contraseña, GitHub ya no las
acepta: usa un Personal Access Token (Settings → Developer settings → Personal
access tokens) o instala GitHub Desktop.

### 2.3 Dale permiso de escritura a los workflows

Los workflows hacen commit de los datos capturados, así que necesitan poder
escribir.

1. En tu repositorio: pestaña **Settings**
2. Menú izquierdo: **Actions** → **General**
3. Baja hasta **Workflow permissions**
4. Selecciona **Read and write permissions**
5. **Save**

### 2.4 Pon tu nombre en la licencia

Ya vienen puestos el nombre en `LICENSE` y la URL del repositorio en la
constante `AGENTE` de `scraper/cfe.py` (el User-Agent con el que el scraper se
identifica ante CFE). Si mueves el repositorio de cuenta, actualiza ambos.

---

## Fase 3 — Cuenta y token de Cloudflare

### 3.1 Crea la cuenta

1. Entra a `dash.cloudflare.com/sign-up`
2. Correo y contraseña. Confirma desde tu bandeja.
3. Si te pregunta por un dominio o por un plan, **sáltalo**. No lo necesitas.

### 3.2 Anota tu Account ID

1. En el panel, menú izquierdo: **Compute (Workers)** → **Workers & Pages**
2. En la columna derecha aparece **Account ID**. Cópialo y guárdalo.

Solo lo vas a necesitar si algo falla en la Fase 4, pero tenerlo a la mano
ahorra tiempo.

### 3.3 Crea el token de API

1. Clic en tu icono de perfil (arriba a la derecha) → **Profile**
2. Pestaña **API Tokens**
3. **Create Token**
4. Busca la plantilla **Edit Cloudflare Workers** y dale **Use template**
5. En *Account Resources*, deja tu cuenta seleccionada
6. En *Zone Resources*, déjalo como viene
7. **Continue to summary** → **Create Token**
8. **Copia el token ahora.** No se vuelve a mostrar. Si lo pierdes, creas otro.

### 3.4 Guárdalo como secret en GitHub

1. En tu repositorio: **Settings**
2. Menú izquierdo: **Secrets and variables** → **Actions**
3. **New repository secret**
4. **Name**: `CLOUDFLARE_API_TOKEN` (exactamente así, respeta mayúsculas)
5. **Secret**: pega el token
6. **Add secret**

---

## Fase 4 — Primer deploy

Vamos a publicar la API con los datos semilla, antes de capturar nada. Así
compruebas que el despliegue funciona en aislado.

### 4.1 Ajusta el nombre del Worker

Abre `worker/wrangler.toml` y cambia la primera línea:

```toml
name = "tarifas-mx"
```

Ese nombre define la URL: `https://tarifas-mx.TUCUENTA.workers.dev`.

### 4.2 Despliega

Desde tu computadora:

```bash
cd worker
npx wrangler login
```

Se abre el navegador. Autoriza. Regresa a la terminal y:

```bash
npx wrangler deploy
```

Al terminar te imprime la URL. Algo como:

```
Published tarifas-mx
  https://tarifas-mx.tucuenta.workers.dev
```

### 4.3 Comprueba que responde

Abre esa URL en el navegador: debe salir la portada.

Y prueba una consulta:

```
https://tarifas-mx.tucuenta.workers.dev/v1/tarifa?region=NOROESTE&anio=2026&mes=3
```

Debe devolver los cargos de marzo 2026.

### 4.4 Guarda el cambio del nombre

```bash
cd ..
git add worker/wrangler.toml LICENSE scraper/cfe.py
git commit -m "Configurar nombre y datos del proyecto"
git push
```

---

## Fase 5 — Backfill de prueba y validación

Este es el paso importante. Vamos a capturar poquito y comprobar que los
números son correctos **antes** de traer diez años.

### 5.1 Lanza el backfill acotado

1. En tu repositorio: pestaña **Actions**
2. Menú izquierdo: **Backfill (manual)**
3. Botón **Run workflow** (a la derecha)
4. Llena los campos:
   - **estados**: `SONORA`
   - **regiones**: `NOROESTE`  (o `TODAS` para no filtrar)
   - **desde**: `2026`
   - **hasta**: déjalo vacío
   - **desplegar**: marcado
5. **Run workflow**

### 5.2 Vigila la corrida

Refresca la página y entra a la corrida que acaba de aparecer. Haz clic en el
job **backfill** para ver el log en vivo.

Tiempos esperados: el catálogo de Sonora son 70 municipios, unos 3 minutos.
Los cargos de 2026 para Noroeste, menos de un minuto.

Si el paso **Verificar que el parser siga funcionando** falla, CFE cambió la
página. Ve a [Problemas comunes](#problemas-comunes).

Si falla **Construir catálogo** o **Capturar cargos**, copia el error del log:
ahí es donde la cadena de postbacks puede necesitar ajuste.

### 5.3 Revisa que los datos llegaron

Al terminar, en la pestaña **Code** de tu repositorio verás un commit nuevo de
`github-actions[bot]`. Entra a `data/tarifas.json` y confirma que hay varios
meses de 2026.

### 5.4 Valida contra un recibo real

**No te saltes esto.** Toma un recibo de CFE de cualquier cliente tuyo en
tarifa GDMTH, mira el mes y la región, y consulta:

```
https://tarifas-mx.tucuenta.workers.dev/v1/tarifa?region=NOROESTE&anio=2026&mes=7
```

Compara los seis cargos contra los que imprime el recibo:

| Campo de la API | Cómo aparece en el recibo |
|---|---|
| `fijo` | Cargo fijo, $/mes |
| `base` | Energía base, $/kWh |
| `intermedia` | Energía intermedia, $/kWh |
| `punta` | Energía punta, $/kWh |
| `distribucion` | Distribución, $/kW |
| `capacidad` | Capacidad, $/kW |

Deben coincidir exactamente. Si no, **detente aquí** y revisa: puede que el
recibo sea de otra región tarifaria, o que el periodo facturado cruce dos
meses y el recibo mezcle dos tarifas.

### 5.5 Prueba los horarios

```
https://tarifas-mx.tucuenta.workers.dev/v1/horarios?region=NOROESTE&fecha=2026-01-15&hora=20:30
```

Debe decir temporada `invierno`, tipo de día `habil` y periodo `punta`.

---

## Fase 6 — Backfill completo

Solo cuando la Fase 5 haya cuadrado.

### 6.1 Decide qué tanto quieres

| Alcance | Estados | Regiones | Desde | Duración aprox. |
|---|---|---|---|---|
| Tu zona, histórico completo | `SONORA,SINALOA` | `NOROESTE` | `2017` | ~15 min |
| País, año en curso | `TODOS` | `TODAS` | `2026` | ~1 h 15 min |
| País, histórico completo | `TODOS` | `TODAS` | `2017` | ~2 h |

> Dos trampas de este formulario:
>
> - Usa las palabras `TODOS` y `TODAS`; si vacías una caja, GitHub la rellena
>   con el valor por omisión.
> - Separa los nombres con **coma**, no con espacio. Muchos llevan espacios
>   dentro: `SAN LUIS POTOSI`, `BAJA CALIFORNIA`, `VALLE DE MEXICO NORTE`.
> - Revisa el campo **desde**: si lo dejas en el valor por omisión no traerás
>   el histórico.

Lo que domina el tiempo es el catálogo de municipios (~2,400 postbacks), no
los cargos. El catálogo se construye una sola vez: si después amplías años, ya
no se repite.

### 6.2 Lánzalo

Actions → **Backfill (manual)** → Run workflow, con los valores que elegiste.

Puedes cerrar el navegador. Corre en los servidores de GitHub.

### 6.3 Comprueba la cobertura

Al terminar:

```
https://tarifas-mx.tucuenta.workers.dev/v1/regiones
```

Te dice qué regiones hay, cuántos periodos tiene cada una y cuántos estados
quedaron en el catálogo.

---

## Fase 7 — Dejar el cron corriendo

Ya está configurado. El workflow `Actualizar tarifas` corre el día 3 de cada
mes a las 9:00 del centro de México, captura lo que falte, hace commit y
redespliega.

### 7.1 Pruébalo una vez a mano

Actions → **Actualizar tarifas** → **Run workflow**. Debería terminar diciendo
que no hubo datos nuevos, porque el backfill ya los trajo. Eso confirma que el
automatismo funciona.

### 7.2 Asegúrate de recibir los avisos

Si el Action falla, GitHub te manda correo. Verifica que esté activo en
github.com/settings/notifications, sección **Actions**.

> GitHub desactiva los cron de repositorios sin actividad después de unos 60
> días. Como este hace commit cada mes, se mantiene solo.

---

## Fase 8 — Conectarlo a un agente

### En Claude

**Plan Pro o Max:**

1. **Customize** → **Connectors**
2. Botón **+** → **Add custom connector**
3. **URL**: `https://tarifas-electricas-mx.contacto-746.workers.dev/mcp`
4. Los campos de OAuth en "Advanced settings" se dejan vacíos: el servidor no
   pide autenticación
5. **Add**

**Plan Team o Enterprise:** solo un Owner puede agregarlo. Primero el Owner va
a Settings → Organization Settings → Connectors y lo da de alta ahí. Después
cada miembro entra a Customize → Connectors, lo busca en la lista (trae la
etiqueta "Custom") y da clic en **Connect**.

**En cada chat hay que encenderlo.** Agregar el conector no lo activa en todas
las conversaciones: dentro del chat, botón **+** abajo a la izquierda → Add
connectors → enciende el que quieras usar.

Ya puedes preguntar cosas como "¿cuánto cuesta el kWh en punta en Navojoa en
marzo de 2026?" o "¿el 15 de agosto a las 8 de la noche estoy en punta en
Noroeste?".

### En otros clientes

Cualquier cliente con soporte MCP funciona apuntando a la misma URL `/mcp`. No
requiere autenticación.

### Desde tus propios sistemas

Usa REST. La especificación está en `/openapi.json`, que puedes cargar en
Postman, Insomnia o el generador de clientes que uses.

---

## Fase 9 — Dominio propio (opcional)

Si quieres una URL como `tarifas.tudominio.com`:

1. El dominio tiene que estar administrado por Cloudflare (agrégalo en el panel
   y cambia los nameservers en tu registrador)
2. **Workers & Pages** → tu worker → **Settings** → **Domains & Routes**
3. **Add** → **Custom domain**
4. Escribe el subdominio y confirma

Cloudflare crea el DNS y el certificado solo. No hay que tocar código y la URL
`.workers.dev` sigue funcionando.

---

## Problemas comunes

### El deploy dice que hay varias cuentas

Agrega tu Account ID (el de la Fase 3.2) a `worker/wrangler.toml`:

```toml
account_id = "tu-account-id"
```

### "Updates were rejected" al hacer git push (en tu máquina)

Alguien empujó antes que tú, casi siempre el propio Action con los datos que
capturó. Se resuelve reintegrando:

```
git pull
git push
```

Costumbre que lo evita: `git pull` **antes** de empezar a trabajar, no después.
El Action escribe en `data/` por su cuenta, así que tu copia local se queda
atrás sola.

### El Action no puede hacer push

Falta el permiso de escritura: Fase 2.3.

### El Action falla en el paso del parser

CFE rediseñó la página. Procedimiento:

1. Abre la página de CFE en el navegador, `Ctrl+S`, guarda sobre
   `scraper/muestra/GranDemandaMTH.html`
2. `cd scraper && python3 test_parser.py` para ver qué se rompió
3. Arregla `scraper/parser.py` hasta que pase
4. Commit y push

Los datos ya capturados no se tocan y la API sigue sirviendo mientras tanto.

### El sitio no recalcula los meses al cambiar de año

No es un firewall ni requiere cookies de ninguna sesión (se sospechó eso al
principio; resultó ser una pista falsa). La causa real: **el control de mes
cambia de nombre según el año elegido.** Para el año en curso la página usa
`Fecha2$ddMes`; para cualquier año pasado, ese control no se renderiza en
absoluto y aparece uno distinto, `MesVerano3$ddMesConsulta`. Si ves que
`meses()` devuelve una lista vacía al cambiar de año, es señal de que
`parser.control_mes()` no está reconociendo el control correcto para esa
página — revisa `scraper/parser.py` y `scraper/test_parser.py`, que incluye
una prueba con datos reales de un año pasado precisamente para esto.

Confirmado con `scraper/diagnostico.py --anio 2019`: sin ninguna cookie ni
configuración especial, el histórico se captura igual.

### Error de TLS: CERTIFICATE_VERIFY_FAILED

El servidor de CFE no manda la cadena completa de certificados. Windows y los
navegadores lo compensan solos, por eso en tu equipo funciona y en Linux no.

Los workflows ya traen un paso que lo resuelve: `preparar_tls.py` descarga los
intermedios faltantes y arma un bundle de CA completo. En local:

```
cd scraper
python3 preparar_tls.py
set REQUESTS_CA_BUNDLE=C:\dev\tarifas-mx\scraper\ca_bundle.pem
```

El script te dice la ruta exacta al terminar.

Si aun así falla, la salida te dice quién emite el certificado. Puede ser que
la raíz no esté en el almacén estándar. Último recurso, agregando `--inseguro`
al comando del scraper, que salta la verificación:

```
python3 actualizar_tarifas.py --regiones NOROESTE --desde 2026 --inseguro
```

Los datos son públicos y de solo lectura, así que el riesgo es bajo, pero
solo úsalo si lo anterior no funcionó.

### El Action falla capturando, con error de conexión

CFE tiene el sitio caído o lento. Vuelve a lanzar el workflow más tarde. Si
persiste, sube la pausa: en `backfill.yml`, cambia `--pausa 2` por `--pausa 4`.

### La API responde 404 con "No hay datos capturados"

Ese periodo no está en la base. La respuesta trae `periodos_disponibles` con
lo que sí hay. Si falta un mes que CFE sí publica, lanza el backfill con ese
año.

### La API responde 404 con "no está en el catálogo"

Ese estado o municipio no se ha capturado. Corre el backfill incluyendo ese
estado, o consulta por `region=` en vez de estado y municipio.

### Los cargos no cuadran con un recibo

Revisa en este orden:

1. Que la región del recibo sea la misma que consultaste
2. Que el periodo facturado no cruce dos meses (los recibos partidos traen
   dos bloques de cargos, uno por mes)
3. Que el recibo sea de la misma tarifa (GDMTH, no GDMTO ni DIST)

---

## Mantenimiento

En condiciones normales el proyecto no necesita atención. Lo único que puede
pedirla:

| Cuándo | Qué hacer |
|---|---|
| CFE rediseña la página | Actualizar la muestra y `parser.py` (ver arriba) |
| CFE publica un año nuevo | Nada: el cron lo detecta solo |
| Quieres agregar otra tarifa | Agregar la URL en `PAGINAS` de `scraper/cfe.py` y correr con `--tarifa GDMTO` |
| Quieres agregar más estados | Backfill manual con esos estados |

Los datos viven versionados en `data/` dentro de git. Aunque apagues el Worker
o abandones el proyecto, el histórico queda ahí y cualquiera puede descargarlo.
