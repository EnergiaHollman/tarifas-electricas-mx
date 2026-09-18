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

    def consultar(self, anio, mes, eid, mid, region_id=None):
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

print()
if fallos:
    print(f"{len(fallos)} prueba(s) fallaron: {', '.join(fallos)}")
    sys.exit(1)
print("Todas las pruebas pasaron.")
