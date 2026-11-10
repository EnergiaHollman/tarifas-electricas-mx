# -*- coding: utf-8 -*-
"""Pruebas del validador de referencias, sin red. `python3 test_validar_referencia.py`."""
import json
import pathlib
import sys

import validar_referencia as V

fallos = []


def check(nombre, obtenido, esperado):
    if obtenido == esperado:
        print(f"  ok   {nombre}")
    else:
        print(f"  FALLA {nombre}\n        esperado: {esperado!r}\n        obtenido: {obtenido!r}")
        fallos.append(nombre)


REF = {"tarifa": "PDBT", "region": "NOROESTE", "tolerancias": {"fijo": 0, "energia": 0.002},
       "meses": {"2026-03": {"fijo": 19.78, "energia": 3.346},
                 "2026-01": {"fijo": [19.78, 77.77], "energia": 3.435}}}


def regs(**por_mes):
    return {f"PDBT|NOROESTE|{m}": {"cargos": c} for m, c in por_mes.items()}


def resultado(registros):
    return {(f["mes"], f["cargo"]): f["ok"] for f in V.validar(registros, REF)}


print("Tolerancias")
r = resultado(regs(**{"2026-03": {"fijo": 19.78, "energia": 3.347},
                      "2026-01": {"fijo": 77.77, "energia": 3.435}}))
check("energía a una milésima de la referencia: ok", r[("2026-03", "energia")], True)
check("fijo exacto: ok", r[("2026-03", "fijo")], True)
check("fijo con lista de valores aceptables (el segundo)", r[("2026-01", "fijo")], True)
r = resultado(regs(**{"2026-03": {"fijo": 19.78, "energia": 3.349},
                      "2026-01": {"fijo": 19.78, "energia": 3.435}}))
check("energía justo en el límite (0.003) falla", r[("2026-03", "energia")], False)
r = resultado(regs(**{"2026-03": {"fijo": 19.79, "energia": 3.346},
                      "2026-01": {"fijo": 50.0, "energia": 3.435}}))
check("fijo con un centavo de diferencia falla (exacto)", r[("2026-03", "fijo")], False)
check("fijo fuera de la lista falla", r[("2026-01", "fijo")], False)
r = resultado(regs(**{"2026-03": {"fijo": 19.78, "energia": 3.348},
                      "2026-01": {"fijo": 19.78, "energia": 3.435}}))
check("energía a exactamente 0.002 pasa (sin error de punto flotante)", r[("2026-03", "energia")], True)

print("\nHuecos y cargos faltantes")
filas = V.validar(regs(**{"2026-03": {"fijo": 19.78}}), REF)
por = {(f["mes"], f["cargo"]): f for f in filas}
check("cargo ausente en el registro falla y lo dice",
      (por[("2026-03", "energia")]["ok"], "no trae el cargo" in por[("2026-03", "energia")]["motivo"]), (False, True))
check("mes sin registro falla",
      (por[("2026-01", "fijo")]["ok"], por[("2026-01", "fijo")]["motivo"]), (False, "no hay registro capturado"))

print("\nArchivo de referencia real")
ref = json.loads((pathlib.Path(__file__).parent / "validacion" / "pdbt_noroeste.json").read_text(encoding="utf-8"))
check("tarifa y región", (ref["tarifa"], ref["region"]), ("PDBT", "NOROESTE"))
check("tolerancias acordadas", ref["tolerancias"], {"fijo": 0, "energia": 0.002})
check("cubre 2025-11 a 2026-10 salvo junio y julio",
      sorted(ref["meses"]) + sorted(ref["sin_referencia"]),
      ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05",
       "2026-08", "2026-09", "2026-10", "2026-06", "2026-07"])
check("sin datos de cliente: solo claves de precios",
      set(c for m in ref["meses"].values() for c in m), {"fijo", "energia"})

print()
if fallos:
    print(f"{len(fallos)} prueba(s) fallaron: {', '.join(fallos)}")
    sys.exit(1)
print("Todas las pruebas pasaron.")
