# -*- coding: utf-8 -*-
"""Pruebas del lector de avisos del DOF, sin red. `python3 test_dof.py`."""
import copy
import pathlib
import sys
from decimal import Decimal

import actualizar_dof as A
import dof

MUESTRA = pathlib.Path(__file__).parent / "muestra"
fallos = []


def check(nombre, obtenido, esperado):
    if obtenido == esperado:
        print(f"  ok   {nombre}")
    else:
        print(f"  FALLA {nombre}\n        esperado: {esperado!r}\n        obtenido: {obtenido!r}")
        fallos.append(nombre)


def leer(nombre):
    return (MUESTRA / nombre).read_text(encoding="latin-1")


print("Aviso de octubre de 2026 (formato reciente)")
a = dof.parsear_aviso(leer("DOF_aviso_2026-10_recortado.html"))
check("periodo", (a["anio"], a["mes"]), (2026, 10))
check("divisiones con su clave", sorted(a["gdmto"]), ["NOROESTE", "ORIENTE"])
o = a["gdmto"]["ORIENTE"]
check("Oriente: cargos por kWh", [o[k] for k in ("transmision", "cenace", "suministro", "generacion")],
      [Decimal("0.1801"), Decimal("0.0076"), Decimal("0.0069"), Decimal("1.087")])
check("Oriente: demanda y fijo", [o["distribucion"], o["capacidad"], o["fijo"]],
      [Decimal("202.45"), Decimal("279.94"), Decimal("636.28")])
check("la suma conserva el 4.º decimal, sin ruido binario", dof.energia_4dec(o), Decimal("1.2816"))
check("Noroeste", dof.energia_4dec(a["gdmto"]["NOROESTE"]), Decimal("1.2606"))

print("\nAviso de septiembre de 2025 (otro encabezado y otros cargos)")
b = dof.parsear_aviso(leer("DOF_aviso_2025-09_recortado.html"))
check("periodo", (b["anio"], b["mes"]), (2025, 9))
check("Oriente 2025-09", dof.energia_4dec(b["gdmto"]["ORIENTE"]), Decimal("1.4527"))

print("\nAvisos que no son lo esperado fallan, no se adivinan")
for nombre, texto in [("sin periodo", "<p>nada</p>"),
                      ("sin divisiones", "<p>a partir del 1 de mayo de 2026</p>"),
                      ("división sin GDMTO", "<p>a partir del 1 de mayo de 2026</p><p>División Oriente Categoría x</p>")]:
    try:
        dof.parsear_aviso(texto)
        check(nombre, "no falló", "ErrorDOF")
    except dof.ErrorDOF:
        check(nombre, "ErrorDOF", "ErrorDOF")
check("nombres con acento y espacios", [dof.clave_region(n) for n in ("Bajío", "Valle de México Norte")],
      ["BAJIO", "VALLE DE MEXICO NORTE"])

print("\nContraste con el portal antes de guardar")
def portal(energia=1.282, **cambios):
    c = {"capacidad": 279.94, "distribucion": 202.45, "energia": energia, "fijo": 636.28}
    c.update(cambios)
    return {"GDMTO|ORIENTE|2026-10": {"cargos": c},
            "GDMTO|OTRA|2026-10": {"cargos": c},
            "GDMTO|ORIENTE|2026-09": {"cargos": c}}

e, p = A.construir(a, portal(), 5802191, "t")
check("cuadra: se guarda con su aviso", e["GDMTO|ORIENTE|2026-10"]["energia_4dec"], 1.2816)
check("solo los meses del aviso y divisiones que ya hay en el portal", sorted(e), ["GDMTO|ORIENTE|2026-10"][:1])
# 'OTRA' no existe en el aviso: se reporta, no se inventa
check("división del portal ausente del aviso: se reporta", [x for x in p if "OTRA" in x] != [], True)
e, p = A.construir(a, portal(energia=1.283), 5802191, "t")
check("la energía del portal no es la suma redondeada: no se guarda", "GDMTO|ORIENTE|2026-10" in e, False)
check("y se reporta", any("1.283" in x for x in p), True)
e, p = A.construir(a, portal(capacidad=280.0), 5802191, "t")
check("capacidad distinta: no se guarda", "GDMTO|ORIENTE|2026-10" in e, False)

print("\nPDBT: fijo y energía como suma de seis cargos")
check("Noroeste 2026-10: seis cargos por kWh", dof.energia_pdbt(a["pdbt"]["NOROESTE"]), Decimal("3.2539"))
check("Oriente 2025-09 (otro formato de aviso): seis cargos", dof.energia_pdbt(b["pdbt"]["ORIENTE"]) > 0, True)
check("Noroeste 2026-10: fijo", a["pdbt"]["NOROESTE"]["fijo"], Decimal("19.78"))
check("Oriente 2025-09 tiene fila de PDBT", "ORIENTE" in b["pdbt"], True)


def pdbt(energia=3.254, fijo=19.78):
    return {"PDBT|NOROESTE|2026-10": {"cargos": {"fijo": fijo, "energia": energia}},
            "PDBT|NOROESTE|2026-09": {"cargos": {"fijo": 0, "energia": 0}}}


e, mal = A.construir(a, pdbt(), 5802191, "t", tarifa="PDBT")
check("PDBT cuadra con el portal (3.2539 redondea a 3.254): se guarda con sus seis componentes",
      (list(e), mal), (["PDBT|NOROESTE|2026-10"], []))
check("PDBT: energia_4dec y componentes", {k: e["PDBT|NOROESTE|2026-10"][k] for k in
      ("energia_4dec", "transmision", "distribucion", "cenace", "suministro", "generacion", "capacidad")},
      {"energia_4dec": 3.2539, "transmision": 0.1801, "distribucion": 0.7753, "cenace": 0.0076,
       "suministro": 0.0069, "generacion": 1.333, "capacidad": 0.951})
e, mal = A.construir(a, pdbt(energia=3.255), 5802191, "t", tarifa="PDBT")
check("PDBT energía distinta: no se guarda y se reporta", (list(e), len(mal)), ([], 1))
e, mal = A.construir(a, pdbt(fijo=20.0), 5802191, "t", tarifa="PDBT")
check("PDBT fijo distinto: no se guarda y se reporta", (list(e), len(mal)), ([], 1))

print("\nvalidacion.json: marcas, huecos e informe")
portal = {"GDMTO|ORIENTE|2025-10": {}, "GDMTO|ORIENTE|2025-11": {}, "PDBT|NOROESTE|2025-10": {},
          "GDMTH|NOROESTE|2025-10": {}}
rec = {"GDMTO|ORIENTE": {"meses": ["2025-10"], "fuente": "x"}}
v = A.anotar_validacion(portal, {"GDMTO|ORIENTE|2025-10", "PDBT|NOROESTE|2025-10"},
                        ["2025-10", "2025-11"], ["NOROESTE", "ORIENTE"], rec, "t")
check("DOF y recibo", v["registros"]["GDMTO|ORIENTE|2025-10"], ["dof", "recibo"])
check("solo DOF", v["registros"]["PDBT|NOROESTE|2025-10"], ["dof"])
check("capturado pero sin validar: sin marcas", "GDMTO|ORIENTE|2025-11" in v["registros"], False)
check("GDMTH no se marca", "GDMTH|NOROESTE|2025-10" in v["registros"], False)
check("hueco: PDBT Noroeste 2025-11", "PDBT|NOROESTE|2025-11" in v["huecos"], True)
check("lo capturado no es hueco", "GDMTO|ORIENTE|2025-10" in v["huecos"], False)
v2 = A.anotar_validacion(portal, set(), ["2025-01", "2025-10"], ["NOROESTE"], {}, "t")
check("meses anteriores a la ventana no generan huecos (solo se valida lo que existe)",
      sorted(k.rsplit("|", 1)[1] for k in v2["huecos"]), ["2025-10"])
v["diferencias"] = []
tabla = A.informe(v, portal, ["NOROESTE", "ORIENTE"], ["2025-10", "2025-11"])
check("el informe tiene una fila por división y tarifa", tabla.count("| ORIENTE |"), 2)

print()
if fallos:
    print(f"{len(fallos)} prueba(s) fallaron.")
    sys.exit(1)
print("Todas las pruebas pasaron.")
