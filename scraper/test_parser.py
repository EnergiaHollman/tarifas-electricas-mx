# -*- coding: utf-8 -*-
"""Pruebas del parser contra la muestra guardada. `python3 test_parser.py`.

Si CFE rediseña la página, guarda la nueva con Ctrl+S en `muestra/`, corre
esto y arregla lo que falle. Es el único punto del proyecto que depende del
HTML de CFE.
"""
import pathlib
import sys

import parser as P

MUESTRA = pathlib.Path(__file__).parent / "muestra" / "GranDemandaMTH.html"
HTML = MUESTRA.read_text(encoding="utf-8", errors="replace")

fallos = []


def check(nombre, obtenido, esperado):
    if obtenido == esperado:
        print(f"  ok   {nombre}")
    else:
        print(f"  FALLA {nombre}\n        esperado: {esperado!r}\n        obtenido: {obtenido!r}")
        fallos.append(nombre)


print("Formulario")
campos = P.campos_formulario(HTML)
check("trae __VIEWSTATE", "__VIEWSTATE" in campos, True)
check("trae __EVENTVALIDATION", "__EVENTVALIDATION" in campos, True)
check("trae __VIEWSTATEGENERATOR", "__VIEWSTATEGENERATOR" in campos, True)
check("trae hidden hdAnio", any(k.endswith("hdAnio") for k in campos), True)
check("trae los 5 desplegables",
      all(k in campos for k in (P.DD_ANIO, P.DD_MES, P.DD_ESTADO, P.DD_MUNICIPIO, P.DD_REGION)), True)

print("\nCatálogos")
anios = [v for v, _, _ in P.opciones(HTML, P.DD_ANIO)]
check("años disponibles", (anios[0], anios[-1], len(anios)), ("2026", "2017", 10))
meses = P.opciones(HTML, P.DD_MES)
# Ojo: en el año en curso el desplegable solo lista los meses ya publicados.
# En la muestra (2026) son enero a octubre. En años cerrados son los 12.
check("meses publicados en la muestra", [t for _, t, _ in meses],
      P.MESES[:10])
check("marzo = valor 3", [v for v, t, _ in meses if t == "MARZO"], ["3"])
estados = P.opciones(HTML, P.DD_ESTADO)
check("32 estados", len(estados), 32)
municipios = P.opciones(HTML, P.DD_MUNICIPIO)
check("70 municipios de Sonora", len(municipios), 70)
check("Navojoa = 1921", [v for v, t, _ in municipios if t == "NAVOJOA"], ["1921"])
check("región seleccionada", P.seleccionado(HTML, P.DD_REGION), ("18", "NOROESTE"))
check("estado seleccionado", P.seleccionado(HTML, P.DD_ESTADO)[1], "SONORA")

print("\nCargos (Noroeste, marzo 2026)")
r = P.parsear_cargos(HTML)
check("hay resultado", r is not None, True)
check("tarifa", r["tarifa"], "GDMTH")
check("región", P.normalizar(r["region"]), "NOROESTE")
check("periodo", r["periodo_cfe"], "MAR-26")
check("6 conceptos", len(r["conceptos"]), 6)
check("cargos", r["cargos"], {
    "fijo": 197.77, "base": 0.9715, "intermedia": 1.5573,
    "punta": 1.7262, "distribucion": 90.85, "capacidad": 392.66})
check("unidades", r["unidades"]["base"], "$/kWh")
check("unidades fijo", r["unidades"]["fijo"], "$/mes")

print("\nHorarios")
h = P.parsear_horarios(HTML)
check("3 zonas", len(h), 3)
sin = [z for z in h if "Central" in z]
check("existe la zona del SIN", len(sin), 1)
z = h[sin[0]]
check("regiones del SIN", z["regiones"],
      ["CENTRAL", "NORESTE", "NOROESTE", "NORTE", "PENINSULAR", "SUR"])
check("verano hábil base", z["temporadas"]["verano"]["dias"]["habil"]["base"], [[0, 360]])
check("verano hábil punta", z["temporadas"]["verano"]["dias"]["habil"]["punta"], [[1200, 1320]])
check("verano hábil intermedia",
      z["temporadas"]["verano"]["dias"]["habil"]["intermedia"], [[360, 1200], [1320, 1440]])
check("verano sábado", z["temporadas"]["verano"]["dias"]["sabado"],
      {"base": [[0, 420]], "intermedia": [[420, 1440]], "punta": []})
check("verano domingo", z["temporadas"]["verano"]["dias"]["domingo"],
      {"base": [[0, 1140]], "intermedia": [[1140, 1440]], "punta": []})
check("invierno hábil punta", z["temporadas"]["invierno"]["dias"]["habil"]["punta"], [[1080, 1320]])
check("invierno sábado punta", z["temporadas"]["invierno"]["dias"]["sabado"]["punta"], [[1140, 1260]])
check("invierno domingo sin punta", z["temporadas"]["invierno"]["dias"]["domingo"]["punta"], [])
check("vigencia de verano trae 'primer domingo de abril'",
      "primer domingo de abril" in z["temporadas"]["verano"]["vigencia"].lower(), True)
check("nombres de zona", set(h),
      {"Región Baja California", "Región Baja California Sur",
       "Regiones Central, Noreste, Noroeste, Norte, Peninsular y Sur"})
check("BC arranca verano el 1 de mayo",
      h["Región Baja California"]["temporadas"]["verano"]["regla"]["inicio"],
      {"tipo": "fijo", "mes": 5, "dia": 1, "desplazamiento": 0})
check("SIN verano: primer domingo de abril",
      z["temporadas"]["verano"]["regla"]["inicio"],
      {"tipo": "n_dia_semana", "n": 1, "mes": 4, "dia_semana": 6, "desplazamiento": 0})
check("SIN verano termina el sábado anterior al último domingo de octubre",
      z["temporadas"]["verano"]["regla"]["fin"],
      {"tipo": "ultimo_dia_semana", "mes": 10, "dia_semana": 6, "desplazamiento": -1})
check("todas las temporadas tienen regla",
      all(t["regla"] for zz in h.values() for t in zz["temporadas"].values()), True)

print()
if fallos:
    print(f"{len(fallos)} prueba(s) fallaron: {', '.join(fallos)}")
    sys.exit(1)
print("Todas las pruebas pasaron.")
