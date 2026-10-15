# -*- coding: utf-8 -*-
"""Pruebas de cruzar_catalogo.py con casos de respuesta conocida.  python3 test_cruzar_catalogo.py"""
import sys
import cruzar_catalogo as C

fallos = []


def check(nombre, obtenido, esperado):
    if obtenido == esperado:
        print(f"  ok   {nombre}")
    else:
        print(f"  FALLA {nombre}\n        esperado: {esperado!r}\n        obtenido: {obtenido!r}")
        fallos.append(nombre)


def mun(*divs):
    return {"opciones": [{"etiqueta": d, "id": "1"} for d in divs]}


CATALOGO = {
    "expansiones": {"BAJIO Y GOLFO CENTRO": ["BAJIO", "GOLFO CENTRO"]},
    "estados": {
        "BAJA CALIFORNIA": {"nombre": "BAJA CALIFORNIA", "municipios": {
            "ENSENADA": mun("BAJA CALIFORNIA"), "TIJUANA": mun("BAJA CALIFORNIA")}},
        "SONORA": {"nombre": "SONORA", "municipios": {
            "PUERTO PENASCO": mun("BAJA CALIFORNIA"), "NAVOJOA": mun("NOROESTE")}},
        "COAHUILA": {"nombre": "COAHUILA", "municipios": {
            "SALTILLO": mun("BAJIO"), "PARRAS": mun("BAJIO")}},
        "ZACATECAS": {"nombre": "ZACATECAS", "municipios": {
            "MAZAPIL": mun("BAJIO Y GOLFO CENTRO"), "JEREZ": mun("BAJIO")}},
        "MICHOACAN": {"nombre": "MICHOACÁN", "municipios": {
            "MORELIA": mun("CENTRO OCCIDENTE"), "SAHUAYO": mun("CENTRO OCCIDENTE")}},
    },
}

print("1. Caso base: todo coincide, con acentos, mayúsculas y nombres oficiales largos")
OFICIAL_OK = {"completo": True, "divisiones": {
    "Baja California": {"Baja California": ["Ensenada", "Tijuana"], "Sonora": ["Puerto Peñasco"]},
    "Noroeste": {"Sonora": ["Navojoa"]},
    "Bajío": {"Coahuila de Zaragoza": ["Saltillo", "Parras"], "Zacatecas": ["Mazapil", "Jerez"]},
    "Golfo Centro": {"Zacatecas": ["Mazapil"]},
    "Centro Occidente": {"Michoacán de Ocampo": ["Morelia", "Sahuayo"]},
}}
r = C.cruzar(CATALOGO, OFICIAL_OK)["resumen"]
check("todos coinciden", (r["faltan_en_catalogo"], r["division_distinta"], r["sobran_en_catalogo"]), (0, 0, 0))
# 10 pares (estado, municipio) distintos: Mazapil figura en dos divisiones pero cuenta una vez.
check("cuenta los municipios oficiales", r["municipios_oficiales_cotejados"], 10)
check("Mazapil (compuesta BAJIO Y GOLFO CENTRO) coincide con sus dos divisiones",
      r["coinciden_en_nombre_y_division"], 10)
check("sin entidades desconocidas", r["entidades_oficiales_sin_equivalente_en_catalogo"], [])

print("\n2. Municipio oficial que el catálogo no tiene (el caso San Felipe / San Quintín)")
o = {"completo": False, "divisiones": {"Baja California": {"Baja California": ["Ensenada", "Tijuana", "San Felipe", "San Quintín"]}}}
inf = C.cruzar(CATALOGO, o)
check("detecta los dos faltantes", sorted(f["municipio"] for f in inf["faltan_en_catalogo"]), ["San Felipe", "San Quintín"])
check("trae la división oficial del faltante", inf["faltan_en_catalogo"][0]["divisiones_oficiales"], ["BAJA CALIFORNIA"])
check("los que sí están no se reportan", inf["resumen"]["coinciden_en_nombre_y_division"], 2)

print("\n3. Municipio de un estado distinto al del catálogo (Puerto Peñasco es de SONORA pero va en la división BC)")
o = {"completo": False, "divisiones": {"Baja California": {"Sonora": ["Puerto Peñasco", "General Plutarco Elías Calles"]}}}
inf = C.cruzar(CATALOGO, o)
check("Peñasco coincide y Plutarco Elías Calles falta",
      ([f["municipio"] for f in inf["faltan_en_catalogo"]], inf["resumen"]["coinciden_en_nombre_y_division"]),
      (["General Plutarco Elías Calles"], 1))

print("\n4. El catálogo lo tiene, pero en otra división")
o = {"completo": False, "divisiones": {"Noroeste": {"Coahuila de Zaragoza": ["Saltillo"]}}}
d = C.cruzar(CATALOGO, o)["division_distinta"]
check("detecta Saltillo", [x["municipio"] for x in d], ["SALTILLO"])
check("dice qué le falta y qué le sobra al catálogo",
      (d[0]["al_catalogo_le_falta"], d[0]["al_catalogo_le_sobra"]), (["NOROESTE"], ["BAJIO"]))

print("\n5. Municipio en dos divisiones oficiales, catálogo con una sola")
o = {"completo": False, "divisiones": {"Bajío": {"Zacatecas": ["Jerez"]}, "Golfo Centro": {"Zacatecas": ["Jerez"]}}}
d = C.cruzar(CATALOGO, o)["division_distinta"]
check("al catálogo le falta GOLFO CENTRO en Jerez", (d[0]["municipio"], d[0]["al_catalogo_le_falta"]), ("JEREZ", ["GOLFO CENTRO"]))

print("\n6. Sobrantes: solo se reportan si la tabla oficial está completa")
o_parcial = {"completo": False, "divisiones": {"Baja California": {"Baja California": ["Ensenada"]}}}
o_total = {"completo": True, "divisiones": {"Baja California": {"Baja California": ["Ensenada"]}}}
check("tabla parcial: no se inventan sobrantes", C.cruzar(CATALOGO, o_parcial)["sobran_en_catalogo"], None)
sob = C.cruzar(CATALOGO, o_total)["sobran_en_catalogo"]
check("tabla completa: Tijuana sobra en el catálogo respecto a lo oficial",
      "TIJUANA" in [s["municipio"] for s in sob], True)

print("\n7. Coincidencias aproximadas: se proponen, nunca se aceptan en silencio")
cat2 = {"expansiones": {}, "estados": {"SONORA": {"nombre": "SONORA", "municipios": {
    "SAN LUIS RIO COLORADO": mun("BAJA CALIFORNIA")}}}}
o = {"completo": False, "divisiones": {"Baja California": {"Sonora": ["San Luis Río Colorados"]}}}  # errata de OCR
inf = C.cruzar(cat2, o)
check("propone la coincidencia y la deja a confirmar", len(inf["coincidencias_aproximadas"]), 1)
check("y no la cuenta como faltante", inf["resumen"]["faltan_en_catalogo"], 0)
cat3 = {"expansiones": {}, "estados": {"SONORA": {"nombre": "SONORA", "municipios": {
    "SAN FELIPE DE JESUS": mun("NOROESTE")}}}}
o = {"completo": False, "divisiones": {"Baja California": {"Sonora": ["San Felipe"]}}}
check("un nombre solo parecido a medias NO se toma por el mismo municipio",
      C.cruzar(cat3, o)["resumen"]["faltan_en_catalogo"], 1)

print("\n8. Entidad oficial que el catálogo no conoce")
o = {"completo": False, "divisiones": {"Bajío": {"Atlántida": ["Ciudad Perdida"]}}}
check("se reporta, no se ignora",
      C.cruzar(CATALOGO, o)["resumen"]["entidades_oficiales_sin_equivalente_en_catalogo"], ["Atlántida"])

print("\n9. Normalización")
check("acentos y mayúsculas", C.norm("  Dolores Hidalgo Cuna de la Independencia  Nacional"), "DOLORES HIDALGO CUNA DE LA INDEPENDENCIA NACIONAL")
check("alias de entidad: México -> ESTADO DE MEXICO", C.clave_entidad("México"), "ESTADO DE MEXICO")
check("alias de entidad: Veracruz de Ignacio de la Llave", C.clave_entidad("Veracruz de Ignacio de la Llave"), "VERACRUZ")

print("\n10. proponer_complemento: alias, ausentes y extras")
def cat_de(estado, nombres, div):
    return {"estado": estado, "nombre": estado, "municipios": {n: {"opciones": [{"etiqueta": div, "id": "1"}]} for n in nombres}}

CAT = {"expansiones": {}, "estados": {
    "NUEVO LEON": cat_de("NUEVO LEON", ["DR. ARROYO", "GRAL. BRAVO", "CARMEN", "MONTERREY"], "GOLFO NORTE"),
    "GUANAJUATO": cat_de("GUANAJUATO", ["SILAO", "DOLORES HIDALGO CUNA DE LA IND", "LEON"], "BAJIO"),
    "OAXACA": cat_de("OAXACA", ["ZAPOTITLAN DEL RIO", "OAXACA DE JUAREZ"], "SURESTE"),
    "SONORA": cat_de("SONORA", ["NAVOJOA"], "NOROESTE"),
}}
OF = {"completo": True, "fuente": "prueba", "divisiones": {
    "Golfo Norte": {"Nuevo León": ["Doctor Arroyo", "General Bravo", "El Carmen", "Monterrey"]},
    "Bajío": {"Guanajuato": ["Silao de la Victoria", "Dolores Hidalgo Cuna de la Independencia Nacional", "León"]},
    "Sureste": {"Oaxaca": ["Oaxaca de Juárez"]},
    "Noroeste": {"Sonora": ["Navojoa"]},
    "Baja California": {"Sonora": ["General Plutarco Elías Calles"]},
}}
comp = C.proponer_complemento(CAT, OF)
al = {e: {(a["oficial"], a["catalogo"]) for a in l} for e, l in comp["alias"].items()}
check("abreviaturas (DR., GRAL.) y artículo (EL CARMEN) emparejan",
      al["NUEVO LEON"], {("Doctor Arroyo", "DR. ARROYO"), ("General Bravo", "GRAL. BRAVO"), ("El Carmen", "CARMEN")})
check("nombre corto del portal vs. nombre largo oficial (SILAO)", ("Silao de la Victoria", "SILAO") in al["GUANAJUATO"], True)
check("nombre truncado a 30 caracteres (prefijo del oficial)",
      ("Dolores Hidalgo Cuna de la Independencia Nacional", "DOLORES HIDALGO CUNA DE LA IND") in al["GUANAJUATO"], True)
check("un municipio que el portal no trae queda como ausente, con su división",
      comp["ausentes"], {"SONORA": [{"oficial": "General Plutarco Elías Calles", "divisiones": ["BAJA CALIFORNIA"]}]})
check("lo que el catálogo tiene y el Acuerdo no queda como extra (solo informativo)",
      comp["extras"], [{"estado": "OAXACA", "municipio": "ZAPOTITLAN DEL RIO"}])
check("lo que ya coincide exacto no genera alias ni ausente (MONTERREY, LEON, NAVOJOA)",
      any(a["oficial"] in ("Monterrey", "León", "Navojoa") for l in comp["alias"].values() for a in l), False)
try:
    C.proponer_complemento(CAT, {"completo": False, "divisiones": OF["divisiones"]})
    check("con la tabla oficial incompleta se niega a clasificar", False, True)
except ValueError:
    check("con la tabla oficial incompleta se niega a clasificar", True, True)
check("dos nombres parecidos pero de municipios distintos NO se emparejan",
      C.proponer_complemento(
          {"expansiones": {}, "estados": {"SONORA": cat_de("SONORA", ["SAN FELIPE DE JESUS"], "NOROESTE")}},
          {"completo": True, "divisiones": {"Baja California": {"Sonora": ["San Felipe"]}, "Noroeste": {"Sonora": ["San Felipe de Jesús"]}}}
      )["ausentes"], {"SONORA": [{"oficial": "San Felipe", "divisiones": ["BAJA CALIFORNIA"]}]})

print()
if fallos:
    print(f"{len(fallos)} prueba(s) fallaron: {', '.join(fallos)}")
    sys.exit(1)
print("Todas las pruebas pasaron.")
