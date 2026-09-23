# -*- coding: utf-8 -*-
"""Pruebas del catálogo y las etiquetas de división. `python3 test_catalogo.py`.

No toca la red: usa una sesión simulada que devuelve el HTML de la muestra,
duplicando la tabla de resultados cuando hace falta imitar a un municipio que
CFE atiende con varias divisiones.
"""
import copy
import pathlib
import re
import sys

import actualizar_tarifas as A
import parser as P

MUESTRA = (pathlib.Path(__file__).parent / "muestra" / "GranDemandaMTH.html")
HTML = MUESTRA.read_text(encoding="utf-8", errors="replace")

fallos = []


def check(nombre, obtenido, esperado):
    if obtenido == esperado:
        print(f"  ok   {nombre}")
    else:
        print(f"  FALLA {nombre}\n        esperado: {esperado!r}\n        obtenido: {obtenido!r}")
        fallos.append(nombre)


def html_con_regiones(nombres):
    """Copia la tabla de resultados una vez por región, con su encabezado."""
    m = re.search(r'<h3[^>]*>.*?</h3>.*?<table class="table table-bordered table-striped".*?</table>',
                  HTML, re.S)
    bloque = m.group(0)
    partes = []
    for n in nombres:
        partes.append(re.sub(r"(<h3[^>]*>).*?(</h3>)", rf"\g<1>{n}\g<2>", bloque, count=1, flags=re.S))
    return HTML[:m.start()] + "".join(partes) + HTML[m.end():]


class SesionFalsa:
    """Imita a SesionCFE: registra las consultas y sirve HTML preparado."""

    def __init__(self, por_opcion):
        self.por_opcion = por_opcion      # id de opción -> lista de regiones
        self.consultas = []
        self.html = HTML

    def consultar(self, anio, mes, eid, mid, region_id=None, region_etiqueta=None):
        self.consultas.append((anio, mes, eid, mid, region_id))
        self.html = html_con_regiones(self.por_opcion.get(region_id, ["Noroeste"]))
        return P.parsear_cargos(self.html)


CATALOGO = {
    "estados": {
        "SONORA": {"id": "26", "nombre": "SONORA", "municipios": {
            "NAVOJOA": {"id": "1921", "nombre": "NAVOJOA",
                        "opciones": [{"id": "18", "etiqueta": "NOROESTE"}]},
        }},
        "MEXICO": {"id": "15", "nombre": "ESTADO DE MÉXICO", "municipios": {
            # Un municipio con dos opciones separadas en el desplegable.
            "TOLUCA": {"id": "1500", "nombre": "TOLUCA", "opciones": [
                {"id": "30", "etiqueta": "VALLE DE MEXICO NORTE"},
                {"id": "31", "etiqueta": "CENTRO OCCIDENTE"}]},
        }},
        "BAJA CALIFORNIA SUR": {"id": "3", "nombre": "BAJA CALIFORNIA SUR", "municipios": {
            # CFE imprime el encabezado "Baja California" aunque la opción
            # seleccionada sea Baja California Sur.
            "COMONDU": {"id": "300", "nombre": "COMONDU", "opciones": [
                {"id": "50", "etiqueta": "BAJA CALIFORNIA SUR"}]},
        }},
        "GUANAJUATO": {"id": "11", "nombre": "GUANAJUATO", "municipios": {
            # Una sola opción cuyo texto abarca dos divisiones.
            "SAN LUIS DE LA PAZ": {"id": "1100", "nombre": "SAN LUIS DE LA PAZ",
                                   "opciones": [{"id": "40", "etiqueta": "BAJIO Y GOLFO CENTRO"}]},
            # El caso que rompía el corte por texto: el prefijo va elidido.
            "CELAYA": {"id": "1101", "nombre": "CELAYA", "opciones": [
                {"id": "41", "etiqueta": "VALLE DE MEXICO CENTRO Y SUR"}]},
        }},
    },
}

POR_OPCION = {
    "18": ["Noroeste"],
    "30": ["Valle de México Norte"],
    "31": ["Centro Occidente"],
    "40": ["Bajío", "Golfo Centro"],
    "41": ["Valle de México Centro", "Valle de México Sur"],
    "50": ["Baja California"],          # encabezado equivocado a propósito
}

print("Lectura de varias tablas")
h = html_con_regiones(["Bajío", "Golfo Centro"])
tablas = P.parsear_todas(h)
check("dos tablas", len(tablas), 2)
check("regiones de cada tabla", [P.normalizar(t["region"]) for t in tablas],
      ["BAJIO", "GOLFO CENTRO"])
check("las dos traen cargos", all(t["cargos"] for t in tablas), True)
check("parsear_cargos sigue dando la primera", P.normalizar(P.parsear_cargos(h)["region"]), "BAJIO")

print("\nPortadores de etiqueta")
port = A.portadores(CATALOGO)
check("una entrada por etiqueta distinta", sorted(port),
      ["BAJA CALIFORNIA SUR", "BAJIO Y GOLFO CENTRO", "CENTRO OCCIDENTE",
       "NOROESTE", "VALLE DE MEXICO CENTRO Y SUR", "VALLE DE MEXICO NORTE"])
check("guarda el id de la opción", port["CENTRO OCCIDENTE"][2], "31")

print("\nResolución de etiquetas")
cat = copy.deepcopy(CATALOGO)
s = SesionFalsa(POR_OPCION)
exp = A.resolver_etiquetas(s, cat, 2026, 3)
check("etiqueta simple", exp["NOROESTE"], ["NOROESTE"])
check("compuesta con prefijo repetido", exp["BAJIO Y GOLFO CENTRO"], ["BAJIO", "GOLFO CENTRO"])
check("compuesta con prefijo elidido", exp["VALLE DE MEXICO CENTRO Y SUR"],
      ["VALLE DE MEXICO CENTRO", "VALLE DE MEXICO SUR"])
check("con una sola tabla manda la opción, no el encabezado",
      exp["BAJA CALIFORNIA SUR"], ["BAJA CALIFORNIA SUR"])
check("una consulta por etiqueta, no por municipio", len(s.consultas), 6)
check("se guarda en el catálogo", cat["expansiones"]["BAJIO Y GOLFO CENTRO"],
      ["BAJIO", "GOLFO CENTRO"])

s2 = SesionFalsa(POR_OPCION)
A.resolver_etiquetas(s2, cat, 2026, 3)
check("no repite lo ya resuelto", len(s2.consultas), 0)

# Una expansión guardada por una versión anterior, con el nombre equivocado.
cat_malo = copy.deepcopy(cat)
cat_malo["expansiones"]["BAJA CALIFORNIA SUR"] = ["BAJA CALIFORNIA"]
s3 = SesionFalsa(POR_OPCION)
exp_malo = A.resolver_etiquetas(s3, cat_malo, 2026, 3)
check("detecta y corrige una expansión heredada mala",
      exp_malo["BAJA CALIFORNIA SUR"], ["BAJA CALIFORNIA SUR"])
check("solo vuelve a consultar la mala", len(s3.consultas), 1)

cat_ok = copy.deepcopy(cat)
s4 = SesionFalsa(POR_OPCION)
A.resolver_etiquetas(s4, cat_ok, 2026, 3, rehacer=True)
check("--reresolver las consulta todas", len(s4.consultas), 6)

print("\nRepresentantes")
reps = A.representantes(cat, exp)
check("una división real del Valle de México Sur, no 'SUR'",
      "SUR" in reps, False)
check("todas las divisiones reales cubiertas", sorted(reps),
      ["BAJA CALIFORNIA SUR", "BAJIO", "CENTRO OCCIDENTE", "GOLFO CENTRO",
       "NOROESTE", "VALLE DE MEXICO CENTRO", "VALLE DE MEXICO NORTE",
       "VALLE DE MEXICO SUR"])
check("BCS no se colapsa dentro de BC", "BAJA CALIFORNIA" in reps, False)
check("prefiere la opción de una sola división",
      reps["VALLE DE MEXICO NORTE"][2], "30")
check("lleva la etiqueta seleccionada", reps["BAJIO"][3], "BAJIO Y GOLFO CENTRO")
check("usa la compuesta cuando no hay otra", reps["BAJIO"][2], "40")

print("\nCompatibilidad con catálogos viejos")
viejo = {"estados": {"SONORA": {"id": "26", "nombre": "SONORA", "municipios": {
    "NAVOJOA": {"id": "1921", "nombre": "NAVOJOA", "region": "NOROESTE", "region_id": "18"}}}}}
check("se leen sin opciones", A.portadores(viejo)["NOROESTE"][2], "18")

print("\nDivisiones de una respuesta")
check("una tabla: manda la opción",
      A.divisiones_de(html_con_regiones(["Baja California"]), "BAJA CALIFORNIA SUR"),
      ["BAJA CALIFORNIA SUR"])
check("dos tablas: mandan los encabezados",
      A.divisiones_de(html_con_regiones(["Bajío", "Golfo Centro"]), "BAJIO Y GOLFO CENTRO"),
      ["BAJIO", "GOLFO CENTRO"])

print("\ncargos_iguales: duplicado sin importancia vs. ambigüedad real")
def tabla_de_prueba(cargos, region="Bajío"):
    return {"cargos": cargos, "region": region, "unidades": {}, "conceptos": [], "periodo_cfe": "FEB-18"}

c = {"fijo": 100.0, "base": 1.0}
check("dos tablas con los mismos cargos: iguales",
      A.cargos_iguales([tabla_de_prueba(c), tabla_de_prueba(dict(c))]), True)
check("dos tablas con cargos distintos: no iguales",
      A.cargos_iguales([tabla_de_prueba(c), tabla_de_prueba({"fijo": 200.0, "base": 2.0})]), False)
check("tres tablas, dos iguales y una distinta: no iguales (basta una para romperlo)",
      A.cargos_iguales([tabla_de_prueba(c), tabla_de_prueba(dict(c)),
                        tabla_de_prueba({"fijo": 999.0})]), False)
check("una sola tabla: siempre 'iguales' (nada con qué comparar)",
      A.cargos_iguales([tabla_de_prueba(c)]), True)

print("\ntabla_definitiva: preferir 'mes_siguiente' cuando CFE republicó el mes")
def tabla_fact(cargos, facturacion):
    d = tabla_de_prueba(cargos)
    d["facturacion"] = facturacion
    return d

check("elige la marcada mes_siguiente",
      A.tabla_definitiva([tabla_fact({"fijo": 1}, "mismo_mes"),
                          tabla_fact({"fijo": 2}, "mes_siguiente")])["cargos"],
      {"fijo": 2})
check("sin ninguna marca (caso normal, no aplica): None",
      A.tabla_definitiva([tabla_de_prueba({"fijo": 1}), tabla_de_prueba({"fijo": 2})]), None)
check("dos marcadas mes_siguiente (no debería pasar, pero no se adivina): None",
      A.tabla_definitiva([tabla_fact({"fijo": 1}, "mes_siguiente"),
                          tabla_fact({"fijo": 2}, "mes_siguiente")]), None)
check("una sola tabla, sin marca: None (no hay nada que elegir, no es este caso)",
      A.tabla_definitiva([tabla_de_prueba({"fijo": 1})]), None)

print("\nDivisiones de una respuesta: cruce contra lo ya conocido (expansiones)")
check("sin regiones_esperadas: se comporta como antes (compatibilidad)",
      A.divisiones_de(html_con_regiones(["Baja California"]), "BAJA CALIFORNIA"),
      ["BAJA CALIFORNIA"])
check("una tabla, coincide con lo esperado: se acepta",
      A.divisiones_de(html_con_regiones(["Baja California"]), "BAJA CALIFORNIA",
                      regiones_esperadas=["BAJA CALIFORNIA"]),
      ["BAJA CALIFORNIA"])

# La corrupción real: "BAJA CALIFORNIA" es una etiqueta de una sola región
# (ya lo sabíamos por expansiones), pero la página devolvió DOS tablas -una
# ajena, de "Valle de México Sur"-. Sin este cruce, el código viejo se
# creía las dos. Con él, se rechaza de plano: no hay forma de saber cuál de
# las dos tablas es la real, así que no se guarda ninguna.
check("dos tablas cuando se esperaba una: se rechaza (None), no se elige ninguna",
      A.divisiones_de(html_con_regiones(["Baja California", "Valle de México Sur"]), "BAJA CALIFORNIA",
                      regiones_esperadas=["BAJA CALIFORNIA"]),
      None)
check("compuesta genuina, coincide en cantidad: se acepta igual que antes",
      A.divisiones_de(html_con_regiones(["Bajío", "Golfo Centro"]), "BAJIO Y GOLFO CENTRO",
                      regiones_esperadas=["BAJIO", "GOLFO CENTRO"]),
      ["BAJIO", "GOLFO CENTRO"])
check("compuesta con una tabla de más también se rechaza",
      A.divisiones_de(html_con_regiones(["Bajío", "Golfo Centro", "Oriente"]), "BAJIO Y GOLFO CENTRO",
                      regiones_esperadas=["BAJIO", "GOLFO CENTRO"]),
      None)

print()
if fallos:
    print(f"{len(fallos)} prueba(s) fallaron: {', '.join(fallos)}")
    sys.exit(1)
print("Todas las pruebas pasaron.")
