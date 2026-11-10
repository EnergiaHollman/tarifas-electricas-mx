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

print("\nDesfase entre el mes del recibo y el del portal")
check("desplazar dentro del año", V.desplazar("2026-05", -1), "2026-04")
check("desplazar cruzando de año hacia atrás", V.desplazar("2026-01", -1), "2025-12")
check("desplazar cruzando de año hacia adelante", V.desplazar("2025-12", 1), "2026-01")
check("desplazar 0 no cambia", V.desplazar("2026-03", 0), "2026-03")
REF_D = {**REF, "desfase_meses": -1}
# El portal publica para 2026-02 lo que el recibo de 2026-03 trae, y para 2025-12 lo del recibo de 2026-01.
portal = regs(**{"2026-02": {"fijo": 19.78, "energia": 3.346}, "2025-12": {"fijo": 77.77, "energia": 3.435}})
filas = V.validar(portal, REF_D)
check("con desfase -1 cada mes se compara con el del portal anterior",
      sorted({(f["mes"], f["mes_portal"]) for f in filas}), [("2026-01", "2025-12"), ("2026-03", "2026-02")])
check("y todo coincide", all(f["ok"] for f in filas), True)
check("el mismo dato sin desfase NO coincide (no es una prueba trivial)",
      all(f["ok"] for f in V.validar(portal, REF_D, desfase=0)), False)

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
check("desfase del piloto declarado en la referencia", ref["desfase_meses"], -1)
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
