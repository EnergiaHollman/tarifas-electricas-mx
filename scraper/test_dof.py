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

print()
if fallos:
    print(f"{len(fallos)} prueba(s) fallaron.")
    sys.exit(1)
print("Todas las pruebas pasaron.")
