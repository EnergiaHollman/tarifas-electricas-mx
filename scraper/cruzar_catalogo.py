#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cruza data/catalogo.json contra la tabla oficial de municipio -> división.

La fuente oficial es el numeral 5.9 ("Correspondencia entre municipios y
divisiones tarifarias") del Anexo Único del Acuerdo de tarifas finales del
suministro básico (A/158/2024 para 2025; CNE CT/11.SE/8-2025 para 2026). El
catálogo sale del desplegable del portal de CFE, que puede ir atrasado frente
a ese Acuerdo (municipios de creación reciente, por ejemplo).

Este módulo es SOLO el motor de comparación: no sabe leer el PDF. Recibe la
tabla oficial ya estructurada:

    {"completo": true | false,
     "divisiones": {"BAJA CALIFORNIA": {"Baja California": ["Ensenada", ...],
                                        "Sonora": ["Puerto Peñasco", ...]},
                    ...}}

"completo" importa: solo si la tabla oficial está completa tiene sentido
reportar municipios que sobran en el catálogo.

    python3 cruzar_catalogo.py oficial.json [data/catalogo.json] [--salida informe.json]
                                   [--complemento data/municipios_complemento.json]
"""
import difflib
import json
import re
import sys
import unicodedata

# Nombre oficial largo (como aparece en el Acuerdo) -> clave del catálogo.
ENTIDAD_ALIAS = {
    "COAHUILA DE ZARAGOZA": "COAHUILA",
    "MICHOACAN DE OCAMPO": "MICHOACAN",
    "VERACRUZ DE IGNACIO DE LA LLAVE": "VERACRUZ",
    "MEXICO": "ESTADO DE MEXICO",
    "ESTADO DE MEXICO": "ESTADO DE MEXICO",
    "CIUDAD DE MEXICO": "CIUDAD DE MEXICO",
    "DISTRITO FEDERAL": "CIUDAD DE MEXICO",
}

# Parecido mínimo (0-1) para proponer que dos nombres son el mismo municipio.
# Las coincidencias aproximadas NUNCA se aceptan en silencio: salen en el
# informe para que una persona las confirme.
UMBRAL_APROXIMADO = 0.88


def norm(texto):
    """MAYÚSCULAS, sin acentos ni signos, espacios colapsados."""
    t = unicodedata.normalize("NFD", str(texto).upper())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^A-Z0-9]+", " ", t)
    return t.strip()


def clave_entidad(nombre):
    n = norm(nombre)
    return ENTIDAD_ALIAS.get(n, n)


def divisiones_de_catalogo(catalogo):
    """{estado: {municipio_norm: {"nombre": str, "divisiones": set}}}.

    Las etiquetas compuestas ("BAJIO Y GOLFO CENTRO") se expanden con la tabla
    `expansiones` del propio catálogo, igual que hace el Worker.
    """
    exp = catalogo.get("expansiones", {})
    salida = {}
    for estado, e in catalogo["estados"].items():
        mun = {}
        for nombre, m in e["municipios"].items():
            divs = set()
            for o in m.get("opciones", []):
                divs |= {norm(d) for d in exp.get(o["etiqueta"], [o["etiqueta"]])}
            mun[norm(nombre)] = {"nombre": nombre, "divisiones": divs}
        salida[estado] = mun
    return salida


def cruzar(catalogo, oficial):
    cat = divisiones_de_catalogo(catalogo)
    completo = bool(oficial.get("completo"))

    # 1) Lo oficial, agrupado por (estado, municipio): un municipio puede
    #    figurar en más de una división.
    oficiales = {}   # (estado, municipio_norm) -> {"nombre", "divisiones": set}
    entidades_desconocidas = set()
    for division, por_entidad in oficial["divisiones"].items():
        for entidad, municipios in por_entidad.items():
            estado = clave_entidad(entidad)
            if estado not in cat:
                entidades_desconocidas.add(entidad)
                continue
            for muni in municipios:
                k = (estado, norm(muni))
                reg = oficiales.setdefault(k, {"nombre": muni, "divisiones": set()})
                reg["divisiones"].add(norm(division))

    faltan, distintas, aproximadas = [], [], []
    vistos_en_catalogo = {estado: set() for estado in cat}

    for (estado, muni_norm), of in sorted(oficiales.items()):
        candidatos = cat[estado]
        if muni_norm in candidatos:
            hallado, via = muni_norm, "exacto"
        else:
            cerca = difflib.get_close_matches(muni_norm, list(candidatos), n=1, cutoff=UMBRAL_APROXIMADO)
            # No proponer un candidato que ya es el match exacto de OTRO oficial.
            if cerca and (estado, cerca[0]) not in oficiales:
                hallado, via = cerca[0], "aproximado"
                aproximadas.append({"estado": estado, "oficial": of["nombre"], "catalogo": candidatos[hallado]["nombre"]})
            else:
                hallado, via = None, None
        if hallado is None:
            faltan.append({"estado": estado, "municipio": of["nombre"], "divisiones_oficiales": sorted(of["divisiones"])})
            continue
        vistos_en_catalogo[estado].add(hallado)
        en_catalogo = candidatos[hallado]["divisiones"]
        if en_catalogo != of["divisiones"]:
            distintas.append({
                "estado": estado, "municipio": candidatos[hallado]["nombre"], "coincidencia": via,
                "oficial": sorted(of["divisiones"]), "catalogo": sorted(en_catalogo),
                "al_catalogo_le_falta": sorted(of["divisiones"] - en_catalogo),
                "al_catalogo_le_sobra": sorted(en_catalogo - of["divisiones"]),
                # Con una tabla oficial PARCIAL, un municipio puede figurar en
                # otra división que aún no se cargó: lo "sobrante" no es fiable.
                "sobrante_fiable": completo,
            })

    sobran = []
    if completo:
        for estado, mun in cat.items():
            for muni_norm, datos in mun.items():
                if muni_norm not in vistos_en_catalogo[estado]:
                    sobran.append({"estado": estado, "municipio": datos["nombre"], "divisiones": sorted(datos["divisiones"])})

    return {
        "resumen": {
            "municipios_oficiales_cotejados": len(oficiales),
            "coinciden_en_nombre_y_division": len(oficiales) - len(faltan) - len(distintas),
            "faltan_en_catalogo": len(faltan),
            "division_distinta": len(distintas),
            "coincidencias_aproximadas_por_confirmar": len(aproximadas),
            "sobran_en_catalogo": len(sobran) if completo else None,
            "tabla_oficial_completa": completo,
            "entidades_oficiales_sin_equivalente_en_catalogo": sorted(entidades_desconocidas),
        },
        "faltan_en_catalogo": faltan,
        "division_distinta": distintas,
        "coincidencias_aproximadas": aproximadas,
        "sobran_en_catalogo": sobran if completo else None,
    }


# --- Del informe al complemento del catálogo ---------------------------------

_ABREV = {"DR": "DOCTOR", "GRAL": "GENERAL", "STA": "SANTA", "STO": "SANTO"}
_RUIDO = {"DE", "DEL", "LA", "LAS", "EL", "LOS", "Y", "HEROICA", "HEROICO", "CIUDAD", "VILLA"}
UMBRAL_PAREJA = 0.80      # parecido mínimo para emparejar un faltante con un sobrante
LARGO_TRUNCADO = 28       # el portal corta los nombres a ~30 caracteres


def _tokens(nombre):
    return [t for t in (_ABREV.get(x, x) for x in norm(nombre).split()) if t not in _RUIDO]


def _parecido(oficial, catalogo):
    """0-1: qué tan probable es que sean el mismo municipio con distinto nombre."""
    a, b = set(_tokens(oficial)), set(_tokens(catalogo))
    por_nombre = difflib.SequenceMatcher(None, norm(oficial), norm(catalogo)).ratio()
    if not a or not b:
        return por_nombre
    contencion = len(a & b) / min(len(a), len(b))
    por_tokens = contencion * 0.9 + 0.1 * difflib.SequenceMatcher(None, " ".join(_tokens(oficial)), " ".join(_tokens(catalogo))).ratio()
    return max(por_tokens, por_nombre)


def _es_truncado(oficial, catalogo):
    """El nombre del portal es un recorte del oficial (el portal corta a ~30 caracteres)."""
    c, o = norm(catalogo), norm(oficial)
    return len(c) >= LARGO_TRUNCADO and o.startswith(c)


def proponer_complemento(catalogo, oficial):
    """Convierte el cruce en las dos listas que el Worker usa de respaldo.

    alias    -> {estado: [{"oficial", "catalogo"}]}   mismo municipio, otro nombre en el portal
    ausentes -> {estado: [{"oficial", "divisiones"}]} el portal no lo trae; la división sale del Acuerdo
    extras   -> [{"estado", "municipio"}]             el catálogo lo tiene y el Acuerdo no (solo se informa)
    divergencias -> {estado: [{"catalogo", "oficial", "portal", "acuerdo"}]}
                    el portal y el Acuerdo asignan divisiones DISTINTAS al mismo municipio. No se
                    corrige ninguno de los dos: se informan, porque son dos fuentes de CFE y hay
                    que decidir cuál manda.
    """
    inf = cruzar(catalogo, oficial)
    if not inf["resumen"]["tabla_oficial_completa"]:
        raise ValueError("la tabla oficial no está marcada como completa: no se puede clasificar 'ausentes' ni 'extras'")
    alias, ausentes = {}, {}
    for a in inf["coincidencias_aproximadas"]:
        alias.setdefault(a["estado"], []).append({"oficial": a["oficial"], "catalogo": a["catalogo"]})
    libres = {}
    for s in inf["sobran_en_catalogo"]:
        libres.setdefault(s["estado"], []).append(s["municipio"])
    for f in inf["faltan_en_catalogo"]:
        estado, nombre = f["estado"], f["municipio"]
        candidatos = libres.get(estado, [])
        mejor = max(candidatos, key=lambda c: _parecido(nombre, c), default=None)
        if mejor is not None and (_es_truncado(nombre, mejor) or _parecido(nombre, mejor) >= UMBRAL_PAREJA):
            alias.setdefault(estado, []).append({"oficial": nombre, "catalogo": mejor})
            candidatos.remove(mejor)
        else:
            ausentes.setdefault(estado, []).append({"oficial": nombre, "divisiones": f["divisiones_oficiales"]})
    extras = [{"estado": e, "municipio": m} for e, ms in sorted(libres.items()) for m in ms]
    ordenar = lambda d, k: {e: sorted(v, key=lambda x: norm(x[k])) for e, v in sorted(d.items())}
    return {"alias": ordenar(alias, "oficial"), "ausentes": ordenar(ausentes, "oficial"), "extras": extras,
            "divergencias": ordenar(_divergencias(catalogo, oficial, alias, extras), "catalogo")}


def _divergencias(catalogo, oficial, alias, extras):
    """Municipios que el portal y el Acuerdo asignan a divisiones distintas.

    Se compara cada clave del catálogo contra su municipio oficial, emparejado por: nombre
    exacto, alias, o nombre truncado a ~30 caracteres (el portal repite algunos municipios con
    el nombre completo y con el recortado, y cada copia puede traer una de sus divisiones).
    """
    cat = divisiones_de_catalogo(catalogo)
    of = {}
    for division, por_entidad in oficial["divisiones"].items():
        for entidad, municipios in por_entidad.items():
            estado = clave_entidad(entidad)
            if estado not in cat:
                continue
            for m in municipios:
                r = of.setdefault(estado, {}).setdefault(norm(m), {"nombre": m, "divisiones": set()})
                r["divisiones"].add(norm(division))

    oficial_de = {}          # (estado, clave del catálogo) -> registro oficial
    for estado, claves in cat.items():
        for n, dato in claves.items():
            if n in of.get(estado, {}):
                oficial_de[(estado, dato["nombre"])] = of[estado][n]
    for estado, lista in alias.items():
        for a in lista:
            if norm(a["oficial"]) in of.get(estado, {}):
                oficial_de.setdefault((estado, a["catalogo"]), of[estado][norm(a["oficial"])])
    for e in extras:       # copia truncada de un municipio que sí está (con su nombre completo)
        candidatos = [r for r in of.get(e["estado"], {}).values() if _es_truncado(r["nombre"], e["municipio"])]
        if len(candidatos) == 1:
            oficial_de.setdefault((e["estado"], e["municipio"]), candidatos[0])

    salida = {}
    for (estado, clave), r in oficial_de.items():
        portal = cat[estado][norm(clave)]["divisiones"]
        if portal != r["divisiones"]:
            salida.setdefault(estado, []).append({"catalogo": clave, "oficial": r["nombre"],
                                                  "portal": sorted(portal), "acuerdo": sorted(r["divisiones"])})
    return salida


def imprimir(informe):
    r = informe["resumen"]
    print("RESUMEN")
    for k, v in r.items():
        print(f"  {k}: {v}")
    for titulo, clave in (("FALTAN EN EL CATÁLOGO", "faltan_en_catalogo"),
                          ("DIVISIÓN DISTINTA", "division_distinta"),
                          ("COINCIDENCIAS APROXIMADAS (confirmar a mano)", "coincidencias_aproximadas"),
                          ("SOBRAN EN EL CATÁLOGO", "sobran_en_catalogo")):
        filas = informe[clave]
        if not filas:
            continue
        print(f"\n{titulo} ({len(filas)})")
        for f in filas:
            print("  ", json.dumps(f, ensure_ascii=False))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    ruta_oficial = args[0]
    ruta_catalogo = args[1] if len(args) > 1 else "data/catalogo.json"
    informe = cruzar(json.load(open(ruta_catalogo, encoding="utf-8")),
                     json.load(open(ruta_oficial, encoding="utf-8")))
    imprimir(informe)
    if "--complemento" in sys.argv:
        destino = sys.argv[sys.argv.index("--complemento") + 1]
        comp = proponer_complemento(json.load(open(ruta_catalogo, encoding="utf-8")),
                                    json.load(open(ruta_oficial, encoding="utf-8")))
        salida = {
            "_comentario": ("Archivo GENERADO por scraper/cruzar_catalogo.py --complemento a partir del "
                            "numeral 5.9 del Acuerdo y REVISADO a mano; el scraper no lo toca. "
                            "alias: mismo municipio con otro nombre en el portal. ausentes: el portal no los "
                            "trae y la division sale del Acuerdo. Se consultan SOLO cuando el catalogo no "
                            "encuentra el municipio. divergencias: el portal y el Acuerdo asignan "
                            "divisiones distintas; la respuesta sigue al portal y lo advierte."),
            "fuente": json.load(open(ruta_oficial, encoding="utf-8")).get("fuente", ""),
            "alias": comp["alias"], "ausentes": comp["ausentes"],
            "divergencias": comp["divergencias"],
        }
        json.dump(salida, open(destino, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\ncomplemento guardado en {destino}: {sum(len(v) for v in comp['alias'].values())} alias, "
              f"{sum(len(v) for v in comp['ausentes'].values())} ausentes, "
              f"{sum(len(v) for v in comp['divergencias'].values())} divergencias, "
              f"{len(comp['extras'])} extras (solo informativos)")
        for e in comp["extras"]:
            print("   extra del catálogo:", json.dumps(e, ensure_ascii=False))
    if "--salida" in sys.argv:
        destino = sys.argv[sys.argv.index("--salida") + 1]
        json.dump(informe, open(destino, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\ninforme guardado en {destino}")
