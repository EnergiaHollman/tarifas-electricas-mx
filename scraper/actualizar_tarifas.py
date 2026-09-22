# -*- coding: utf-8 -*-
"""Captura cargos y horarios y los escribe en data/.

Los cargos dependen de la región tarifaria, no del municipio, así que basta
un municipio representativo por región: son ~8 consultas por mes en vez de
2,400. El representativo sale del catálogo.

    # backfill de una región
    python3 actualizar_tarifas.py --regiones NOROESTE --desde 2024

    # backfill completo (tarda; hazlo una vez)
    python3 actualizar_tarifas.py --desde 2017

    # lo que corre el cron mensual: solo lo que falte
    python3 actualizar_tarifas.py --faltantes

Nunca reescribe un registro ya capturado salvo con --rehacer: un mes cerrado
no cambia, y si cambia quieres enterarte, no que se sobreescriba callado.
"""
import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

import cfe
import parser as P

DATA = pathlib.Path(__file__).resolve().parents[1] / "data"
CATALOGO = DATA / "catalogo.json"
TARIFAS = DATA / "tarifas.json"
HORARIOS = DATA / "horarios.json"


def lista(texto):
    """'A, B , C' -> ['A', 'B', 'C'].

    Se separa por comas y no por espacios porque casi la mitad de los nombres
    los llevan: "SAN LUIS POTOSI", "VALLE DE MEXICO NORTE", "BAJA CALIFORNIA".
    """
    if not texto:
        return []
    return [p.strip() for p in texto.split(",") if p.strip()]


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cargar(ruta, vacio):
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    return vacio


def escribir(ruta, datos):
    DATA.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True),
                    encoding="utf-8")


def opciones_de(municipio):
    """Compatibilidad con catálogos viejos, que traían un solo campo region."""
    if municipio.get("opciones"):
        return municipio["opciones"]
    if municipio.get("region"):
        return [{"id": municipio.get("region_id"), "etiqueta": municipio["region"]}]
    return []


def portadores(catalogo):
    """{etiqueta: (estado_id, municipio_id, opcion_id, nombre)} para resolverlas.

    Una etiqueta como "BAJIO Y GOLFO CENTRO" no se puede partir por texto: CFE
    elide el prefijo compartido ("VALLE DE MEXICO CENTRO Y SUR" son Centro y
    Sur del Valle de México, no "Sur"). La única fuente fiable son los
    encabezados que devuelve la página, así que se consulta una vez por
    etiqueta y se guarda la equivalencia.
    """
    fuera = {}
    for estado in catalogo.get("estados", {}).values():
        for municipio in estado["municipios"].values():
            for o in opciones_de(municipio):
                fuera.setdefault(o["etiqueta"],
                                 (estado["id"], municipio["id"], o["id"],
                                  f"{municipio['nombre']}, {estado['nombre']}"))
    return fuera


def resolver_etiquetas(s, catalogo, anio, mes, rehacer=False):
    """Aprende qué regiones reales hay detrás de cada etiqueta del catálogo."""
    if rehacer:
        catalogo["expansiones"] = {}
    expansiones = catalogo.setdefault("expansiones", {})
    for etiqueta, (eid, mid, oid, nombre) in sorted(portadores(catalogo).items()):
        previa = expansiones.get(etiqueta)
        if previa is not None:
            # Una expansión de un solo elemento tiene que ser la etiqueta
            # misma. Si no lo es, viene de cuando se creía en el encabezado de
            # la página, y hay que volver a resolverla.
            if len(previa) == 1 and P.normalizar(previa[0]) != etiqueta:
                print(f"   corrigiendo {etiqueta}: estaba guardada como {previa[0]}")
                del expansiones[etiqueta]
            else:
                continue
        try:
            s.consultar(anio, mes, eid, mid, region_id=oid, region_etiqueta=etiqueta)
        except cfe.ErrorCFE as e:
            print(f"   ! {etiqueta}: {e}")
            continue
        reales = divisiones_de(s.html, etiqueta)
        if not reales:
            print(f"   ? {etiqueta}: sin resultados en {anio}-{mes:02d}")
            continue
        expansiones[etiqueta] = reales
        if reales != [etiqueta]:
            print(f"   {etiqueta}  ->  {', '.join(reales)}")
    return expansiones


def divisiones_de(html, etiqueta, regiones_esperadas=None):
    """Divisiones que responden a una selección concreta del desplegable.

    Con una sola tabla, la división es la etiqueta que se seleccionó: el
    encabezado de la página no es de fiar (para Baja California Sur imprime
    "Baja California"). Con varias tablas la etiqueta es compuesta y solo los
    encabezados dicen cuáles son.

    regiones_esperadas, si se da, es la lista YA RESUELTA (por
    resolver_etiquetas, antes de esta llamada) de a qué división real
    corresponde esta etiqueta. Es la verificación más fuerte que hay: no
    depende de leer nada de la página en el momento, solo de contar. Pasó de
    verdad que una etiqueta "pura" (una sola región, como "BAJA CALIFORNIA")
    devolvió DOS tablas en cierto tramo de una corrida -probablemente el
    desplegable derivó a otra selección sin que el guardián de nombre lo
    notara- y el código viejo, sin nada con qué comparar, se las creyó las
    dos. Si el número de tablas no coincide con el número ya conocido de
    regiones, se devuelve None: "no confíes en esto".
    """
    tablas = [t for t in P.parsear_todas(html) if t["cargos"]]
    if not tablas:
        return []
    if regiones_esperadas is not None and len(tablas) != len(regiones_esperadas):
        return None
    if len(tablas) == 1:
        return [P.normalizar(etiqueta)]
    return [P.normalizar(t["region"]) for t in tablas if t["region"]]


def representantes(catalogo, expansiones):
    """{REGION: (estado_id, municipio_id, opcion_id, etiqueta, nombre)}: uno por región.

    Se prefiere una opción que cubra una sola división: es más rápida y no
    deja ambigüedad. Las compuestas solo se usan si no hay otra.
    """
    puros, mixtos = {}, {}
    for estado in catalogo.get("estados", {}).values():
        for municipio in estado["municipios"].values():
            for o in opciones_de(municipio):
                reales = expansiones.get(o["etiqueta"], [o["etiqueta"]])
                destino = puros if len(reales) == 1 else mixtos
                for r in reales:
                    destino.setdefault(r, (estado["id"], municipio["id"], o["id"],
                                           o["etiqueta"],
                                           f"{municipio['nombre']}, {estado['nombre']}"))
    fuera = dict(mixtos)
    fuera.update(puros)
    return fuera


def clave(tarifa, region, anio, mes):
    return f"{tarifa}|{region}|{anio:04d}-{mes:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tarifa", default="GDMTH", choices=sorted(cfe.PAGINAS))
    ap.add_argument("--regiones", help="separadas por coma; omitir = todas las del catálogo")
    ap.add_argument("--desde", type=int, help="año inicial")
    ap.add_argument("--hasta", type=int, help="año final")
    ap.add_argument("--faltantes", action="store_true",
                    help="solo lo que no esté capturado (modo cron)")
    ap.add_argument("--rehacer", action="store_true")
    ap.add_argument("--reresolver", action="store_true",
                    help="vuelve a resolver todas las etiquetas de división")
    ap.add_argument("--olvidar", metavar="REGIONES",
                    help="separadas por coma; borra sus registros antes de capturar")
    ap.add_argument("--limpiar-todo", action="store_true",
                    help="vacía TODOS los registros de tarifas.json antes de capturar "
                         "(el catálogo y horarios no se tocan). Con --rehacer, un mes "
                         "que falla al reverificar simplemente no se sobreescribe, así "
                         "que un dato viejo contaminado podría sobrevivir; --limpiar-todo "
                         "no deja ningún dato viejo por delante, contaminado o no. "
                         "Como tarifas.json está versionado en git, es reversible.")
    ap.add_argument("--pausa", type=float, default=1.5)
    ap.add_argument("--inseguro", action="store_true",
                    help="salta la verificación TLS; último recurso")
    args = ap.parse_args()

    catalogo = cargar(CATALOGO, None)
    if not catalogo:
        sys.exit("falta data/catalogo.json: corre construir_catalogo.py primero")

    tarifas = cargar(TARIFAS, {"actualizado": None, "fuente": cfe.PAGINAS[args.tarifa],
                               "registros": {}})
    registros = tarifas["registros"]

    if args.limpiar_todo:
        n = len(registros)
        registros.clear()
        escribir(TARIFAS, tarifas)   # visible de inmediato, no solo al final de la corrida
        print(f"Limpiados TODOS los registros ({n}). Arrancando tarifas.json desde cero.")

    if args.olvidar:
        borrar = {P.normalizar(r) for r in lista(args.olvidar)}
        fuera = [k for k, v in registros.items() if P.normalizar(v["region"]) in borrar]
        for k in fuera:
            del registros[k]
        print(f"Olvidados {len(fuera)} registro(s) de: {', '.join(sorted(borrar))}")

    s = cfe.SesionCFE(args.tarifa, pausa=args.pausa, verificar_tls=not args.inseguro).abrir()

    # Los horarios vienen en cualquier respuesta de la página.
    escribir(HORARIOS, {"generado": ahora(), "fuente": s.url, "zonas": s.horarios()})
    print(f"horarios -> {HORARIOS.name}")

    # Al cargar la página, el desplegable de años puede traer solo el año en
    # curso y ampliarse después de seleccionar ubicación. Por eso el rango se
    # toma de lo que pidió el usuario y se contrasta región por región.
    ofrecidos = sorted(s.anios(), reverse=True)
    print(f"Años ofrecidos al cargar: {ofrecidos}")
    desde = args.desde or max(ofrecidos)
    hasta = args.hasta or max(ofrecidos)
    if desde > hasta:
        sys.exit(f"rango vacío: {desde}–{hasta}")
    anios_pedidos = list(range(desde, hasta + 1))

    # Qué divisiones reales hay detrás de cada etiqueta. Una consulta por
    # etiqueta desconocida, y queda guardado en el catálogo.
    print("\nResolviendo etiquetas de división")
    anio_ref = max(ofrecidos)
    s.poner_anio(anio_ref)
    mes_ref = max(s.meses()[:-1] or s.meses())      # el último suele estar vacío
    expansiones = resolver_etiquetas(s, catalogo, anio_ref, mes_ref,
                                     rehacer=args.reresolver)
    escribir(CATALOGO, catalogo)
    reales = sorted({r for v in expansiones.values() for r in v})
    print(f"   {len(expansiones)} etiqueta(s) -> {len(reales)} división(es) reales")

    reps = representantes(catalogo, expansiones)
    if args.regiones:
        querer = {P.normalizar(r) for r in lista(args.regiones)}
        faltan = querer - set(reps)
        if faltan:
            sys.exit(f"no hay municipios en el catálogo para: {', '.join(sorted(faltan))}")
        reps = {k: v for k, v in reps.items() if k in querer}
    if not reps:
        sys.exit("el catálogo no tiene regiones")

    nuevos = omitidos = vacios = sospechosos = 0
    for region, (eid, mid, oid, etiqueta_division, etiqueta) in sorted(reps.items()):
        print(f"\n== {region}  ({etiqueta})")
        for anio in anios_pedidos:
            if not (desde <= anio <= hasta):
                continue
            # El sitio calcula los meses de un año ANTES de que haya ubicación
            # elegida: el flujo real es año, mes, estado, municipio, división
            # (lo confirmó el usuario probando el sitio a mano). Seleccionar
            # el año con una ubicación ya puesta deja los meses vacíos. Por
            # eso cada año arranca desde una página recién cargada.
            s.abrir()
            s.poner_anio(anio)
            seleccionado = s._actual(P.DD_ANIO)[0]
            if seleccionado != str(anio):
                print(f"   {anio}  no quedó seleccionado (quedó {seleccionado}); se omite")
                continue
            meses = s.meses()
            if not meses:
                print(f"   {anio}  el sitio no ofrece meses; se omite")
                continue
            for mes in meses:              # CFE solo lista los meses publicados
                k = clave(args.tarifa, region, anio, mes)
                if k in registros and not args.rehacer:
                    omitidos += 1
                    continue
                if args.faltantes and k in registros:
                    omitidos += 1
                    continue
                # consultar() ya sigue el orden año, mes, estado, municipio,
                # división; año quedó fijo arriba, así que solo avanza mes y
                # ubicación. region_etiqueta hace que reviente aquí, fuerte y
                # claro, si la sesión trae otra división seleccionada -pasó
                # de verdad en un backfill real- en vez de guardar en
                # silencio el dato de la región equivocada.
                try:
                    s.consultar(anio, mes, eid, mid, region_id=oid, region_etiqueta=etiqueta_division)
                except cfe.ErrorCFE as e:
                    print(f"   {anio}-{mes:02d}  ! SOSPECHOSO, no se guarda: {e}")
                    sospechosos += 1
                    continue
                tablas = [t for t in P.parsear_todas(s.html) if t["cargos"]]
                if not tablas:
                    print(f"   {anio}-{mes:02d}  sin publicación")
                    vacios += 1
                    continue
                # Con una tabla, la división es la que se seleccionó; con
                # varias, la etiqueta era compuesta y cada encabezado manda.
                # regiones_esperadas es lo que YA SABÍAMOS (de resolver_
                # etiquetas, antes de este bucle) que esta etiqueta debía
                # devolver. Si el número de tablas no coincide -pasó de
                # verdad: una etiqueta de una sola región devolvió dos
                # tablas, una ajena, sin que el guardián de nombre lo
                # notara- no se confía en nada de lo recibido.
                regiones_esperadas = expansiones.get(P.normalizar(etiqueta_division), [etiqueta_division])
                nombres = divisiones_de(s.html, etiqueta_division, regiones_esperadas=regiones_esperadas)
                if nombres is None:
                    vistas = [P.normalizar(t["region"] or "?") for t in tablas]
                    print(f"   {anio}-{mes:02d}  ! SOSPECHOSO, no se guarda: se esperaban "
                          f"{len(regiones_esperadas)} tabla(s) ({', '.join(regiones_esperadas)}) "
                          f"y llegaron {len(tablas)} ({', '.join(vistas)})")
                    sospechosos += 1
                    continue
                guardadas = []
                for real, t in zip(nombres, tablas):
                    if not real:
                        continue
                    kr = clave(args.tarifa, real, anio, mes)
                    if kr in registros and not args.rehacer:
                        continue
                    registros[kr] = {
                        "tarifa": args.tarifa, "region": real,
                        "anio": anio, "mes": mes,
                        "periodo_cfe": t["periodo_cfe"],
                        "cargos": t["cargos"], "unidades": t["unidades"],
                        "conceptos": t["conceptos"],
                        "municipio_consultado": etiqueta,
                        "fuente": s.url, "fecha_captura": ahora(),
                    }
                    guardadas.append(real)
                    nuevos += 1
                if not guardadas:
                    omitidos += 1
                    continue
                for real in guardadas:
                    cg = registros[clave(args.tarifa, real, anio, mes)]["cargos"]
                    print(f"   {anio}-{mes:02d}  {real}  " +
                          "  ".join(f"{k2}={v}" for k2, v in cg.items()))
                tarifas["actualizado"] = ahora()
                escribir(TARIFAS, tarifas)   # guardado incremental: reanudable

    tarifas["actualizado"] = ahora()
    escribir(TARIFAS, tarifas)
    print(f"\n{nuevos} nuevo(s), {omitidos} ya estaban, {vacios} sin publicación, "
          f"{sospechosos} sospechoso(s) descartados. Total en base: {len(registros)}")
    if sospechosos:
        print("\nHubo meses donde la sesión mostró una división distinta a la pedida.")
        print("No se guardaron (mejor un hueco que un dato mal etiquetado), pero conviene")
        print("investigar: revisa las líneas '! SOSPECHOSO' de este mismo log para ver")
        print("exactamente qué región se pidió y cuál mostró la página. Puede ser un")
        print("problema pasajero del sitio; relanzar con --rehacer para esas regiones")
        print("suele bastar. Si --cookies/CFE_COOKIES está en uso, prueba sin ella primero:")
        print("se confirmó que el histórico se captura bien sin ninguna cookie.")
        sys.exit(1)   # falla de verdad: hay que mirar el log, no solo relanzar
    if nuevos == 0 and not omitidos:
        sys.exit(2)      # el cron lo marca como falla: algo cambió en CFE


if __name__ == "__main__":
    main()
