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

# Página con un año PASADO seleccionado. El control de mes es otro por
# completo (MesVerano3$ddMesConsulta): Fecha2$ddMes ni siquiera existe aquí.
# Descubierto porque el scraper buscaba el control equivocado y por eso
# nunca lograba traer histórico.
MUESTRA_HIST = pathlib.Path(__file__).parent / "muestra" / "GranDemandaMTH_historico.html"
HTML_HIST = MUESTRA_HIST.read_text(encoding="utf-8", errors="replace") if MUESTRA_HIST.exists() else None

# Un mes que CFE republicó (febrero de 2018, Noroeste): la página trae DOS
# tablas de resultados, cada una precedida por su propio texto "2.1.1 ..." /
# "2.1.2 ...". Confirmado contra el sitio real por el usuario del proyecto.
MUESTRA_FACT = pathlib.Path(__file__).parent / "muestra" / "GranDemandaMTH_facturacion.html"
HTML_FACT = MUESTRA_FACT.read_text(encoding="utf-8", errors="replace") if MUESTRA_FACT.exists() else None

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

print("\nControl de mes según el año (año actual vs. histórico)")
check("año actual usa Fecha2$ddMes", P.control_mes(HTML), P.DD_MES)
if HTML_HIST is None:
    print("  (omitida: falta muestra/GranDemandaMTH_historico.html)")
    fallos.append("muestra histórica ausente")
else:
    check("año pasado usa MesVerano3$ddMesConsulta", P.control_mes(HTML_HIST), P.DD_MES_HISTORICO)
    check("Fecha2$ddMes no existe en la página histórica",
          P.seleccionado(HTML_HIST, P.DD_MES)[0], None)
    meses_hist = [t for _, t, _ in P.opciones(HTML_HIST, P.DD_MES_HISTORICO)]
    check("12 meses en el control histórico", len(meses_hist), 12)
    check("mayo seleccionado", P.seleccionado(HTML_HIST, P.DD_MES_HISTORICO), ("5", "MAYO"))

    r_hist = P.parsear_cargos(HTML_HIST)
    check("hay resultado histórico", r_hist is not None, True)
    check("región histórica", P.normalizar(r_hist["region"]), "NOROESTE")
    check("periodo histórico", r_hist["periodo_cfe"], "MAY-19")
    check("cargos de mayo 2019, Noroeste (dato real de CFE)", r_hist["cargos"], {
        "fijo": 611.85, "base": 0.8801, "intermedia": 1.4083,
        "punta": 1.5606, "distribucion": 87.59, "capacidad": 354.09})

print("\nUn mes republicado por CFE trae dos tablas (febrero de 2018, Noroeste)")
if HTML_FACT is None:
    print("  (omitida: falta muestra/GranDemandaMTH_facturacion.html)")
    fallos.append("muestra de facturación ausente")
else:
    tablas_fact = P.parsear_todas(HTML_FACT)
    check("dos tablas, no una", len(tablas_fact), 2)
    check("las dos son de la misma región", {P.normalizar(t["region"]) for t in tablas_fact}, {"NOROESTE"})
    facturaciones = {t["facturacion"] for t in tablas_fact}
    check("una marcada 'mismo_mes' y otra 'mes_siguiente'",
          facturaciones, {"mismo_mes", "mes_siguiente"})

    por_tipo = {t["facturacion"]: t for t in tablas_fact}
    check("mismo_mes: cargos exactos de la tabla 2.1.1", por_tipo["mismo_mes"]["cargos"], {
        "fijo": 591.73, "base": 0.6011, "intermedia": 0.87,
        "punta": 1.0022, "distribucion": 84.16, "capacidad": 195.84})
    check("mes_siguiente: cargos exactos de la tabla 2.1.2 (la que casi siempre se factura)",
          por_tipo["mes_siguiente"]["cargos"], {
        "fijo": 591.73, "base": 0.5589, "intermedia": 0.851,
        "punta": 0.9353, "distribucion": 84.16, "capacidad": 195.84})
    check("los cargos fijos coinciden entre ambas (correcto: el ajuste es solo en energía)",
          por_tipo["mismo_mes"]["cargos"]["fijo"], por_tipo["mes_siguiente"]["cargos"]["fijo"])

    check("un mes normal (marzo 2026, una sola tabla) no trae marca de facturación",
          P.parsear_cargos(HTML)["facturacion"], None)

print("\nRegresión de GDMTH: el parser generalizado extrae lo mismo que el anterior")
# muestra/dorado_gdmth.json es la salida del parser ANTERIOR (el de posiciones
# fijas) sobre las tres muestras de GDMTH, congelada antes de generalizarlo.
# Si esto falla, cambió la forma de los datos que ya consume Dashboard.
import json
DORADO = json.loads((pathlib.Path(__file__).parent / "muestra" / "dorado_gdmth.json")
                    .read_text(encoding="utf-8"))
for nombre in ("GranDemandaMTH", "GranDemandaMTH_historico", "GranDemandaMTH_facturacion"):
    h = (pathlib.Path(__file__).parent / "muestra" / f"{nombre}.html").read_text(
        encoding="utf-8", errors="replace")
    check(f"{nombre}: tablas idénticas a las del parser anterior",
          P.parsear_todas(h), DORADO[nombre]["todas"])
    check(f"{nombre}: horarios idénticos", P.parsear_horarios(h), DORADO[nombre]["horarios"])

print("\nGDMTO (Noroeste, septiembre 2026): sin horarios, cuatro cargos")
HTML_GDMTO = (pathlib.Path(__file__).parent / "muestra" / "GDMTO_2026-09_NOROESTE.html"
              ).read_text(encoding="utf-8", errors="replace")
r = P.parsear_cargos(HTML_GDMTO)
check("tarifa", r["tarifa"], "GDMTO")
check("región", P.normalizar(r["region"]), "NOROESTE")
check("periodo", r["periodo_cfe"], "SEP-26")
check("cargos completos (antes solo sobrevivía 'fijo')", r["cargos"], {
    "fijo": 197.77, "energia": 1.261, "distribucion": 90.85, "capacidad": 327.96})
check("4 conceptos", len(r["conceptos"]), 4)
check("conceptos con la forma de siempre", r["conceptos"][1],
      {"int_horario": "-", "cargo": "Variable (Energía)", "unidades": "$/kWh", "valor": 1.261})
check("unidades", r["unidades"], {"fijo": "$/mes", "energia": "$/kWh",
                                   "distribucion": "$/kW", "capacidad": "$/kW"})

print("\nPDBT (Noroeste, marzo 2026): sin horarios ni demanda")
HTML_PDBT = (pathlib.Path(__file__).parent / "muestra" / "PDBT_2026-03_NOROESTE.html"
             ).read_text(encoding="utf-8", errors="replace")
r = P.parsear_cargos(HTML_PDBT)
check("tarifa", r["tarifa"], "PDBT")
check("periodo", r["periodo_cfe"], "MAR-26")
check("cargos completos (antes solo sobrevivía 'fijo')", r["cargos"], {"fijo": 19.78, "energia": 3.347})
check("2 conceptos", len(r["conceptos"]), 2)

print("\nUna tabla con encabezado irreconocible no se inventa")
check("sin columnas Cargo/Unidades: None",
      P.parsear_todas("<table class='table-striped'><tr><th>A</th><th>B</th></tr>"
                      "<tr><td>1</td><td>2</td></tr></table>"), [])

print("\nDAC (tabla por región de DAC, sin ubicación)")
HTML_DAC = (pathlib.Path(__file__).parent / "muestra" / "DAC_2026-09.html").read_text(encoding="utf-8", errors="replace")
HTML_DAC_2019 = (pathlib.Path(__file__).parent / "muestra" / "DAC_2019-09.html").read_text(encoding="utf-8", errors="replace")
check("año actual: control de mes de DAC", P.control_mes(HTML_DAC), P.DD_MES_DAC)
check("año pasado: el mismo control histórico de siempre", P.control_mes(HTML_DAC_2019), P.DD_MES_HISTORICO)
dac = {t["region"]: t for t in P.parsear_dac(HTML_DAC)}
check("seis regiones de DAC", sorted(dac), ["BAJA CALIFORNIA", "BAJA CALIFORNIA SUR", "CENTRAL",
                                            "NOROESTE", "NORTE Y NORESTE", "SUR Y PENINSULAR"])
check("periodo derivado del mes seleccionado", {t["periodo_cfe"] for t in dac.values()}, {"SEP-26"})
check("Noroeste 2026-09 (publicado por CFE)", dac["NOROESTE"]["cargos"], {"fijo": 145.85, "energia": 6.143})
check("Central, Norte y Noreste, Sur y Peninsular",
      [dac[r]["cargos"]["energia"] for r in ("CENTRAL", "NORTE Y NORESTE", "SUR Y PENINSULAR")],
      [6.557, 5.984, 6.08])
check("Baja California trae verano y fuera de verano", dac["BAJA CALIFORNIA"]["cargos"],
      {"fijo": 145.85, "energia_verano": 6.376, "energia_fuera_verano": 5.475})
check("Baja California Sur", dac["BAJA CALIFORNIA SUR"]["cargos"],
      {"fijo": 145.85, "energia_verano": 6.948, "energia_fuera_verano": 5.475})
check("unidades", dac["NOROESTE"]["unidades"], {"fijo": "$/mes", "energia": "$/kWh"})
check("conceptos con la forma de siempre", dac["NOROESTE"]["conceptos"][1],
      {"int_horario": "-", "cargo": "Variable (Energía)", "unidades": "$/kWh", "valor": 6.143})
check("conceptos de temporada llevan Verano / Fuera de verano",
      [c["int_horario"] for c in dac["BAJA CALIFORNIA"]["conceptos"]], ["-", "Verano", "Fuera de verano"])
dac19 = {t["region"]: t for t in P.parsear_dac(HTML_DAC_2019)}
check("2019-09 Noroeste (el recibo real de septiembre de 2019 lo reproduce)",
      dac19["NOROESTE"]["cargos"], {"fijo": 107.74, "energia": 4.305})
check("la misma forma en 2019", sorted(dac19) == sorted(dac), True)
check("una página de GDMTH no trae tablas de DAC", P.parsear_dac(HTML), [])
check("una página vacía tampoco", P.parsear_dac("<html></html>"), [])

print()
if fallos:
    print(f"{len(fallos)} prueba(s) fallaron: {', '.join(fallos)}")
    sys.exit(1)
print("Todas las pruebas pasaron.")
