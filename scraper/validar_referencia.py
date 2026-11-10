# -*- coding: utf-8 -*-
"""Compara lo capturado en data/tarifas.json con precios de referencia sacados
de recibos reales. Solo lectura.

    python3 validar_referencia.py validacion/pdbt_noroeste.json

El archivo de referencia dice tarifa, region, tolerancia por cargo y, por mes,
el valor esperado de cada cargo (un numero, o una lista de valores aceptables).

`desfase_meses` (0 si falta) dice a que mes del portal corresponde cada mes de la
referencia: con -1, el recibo cuyo periodo termina en 2026-02 se compara con las
cuotas que el portal publica para 2026-01. `--desfase N` lo sustituye desde la
linea de comandos, para comprobar rapido otra hipotesis.
Sale con codigo 1 si algun mes difiere o falta en los datos. Los meses de
`sin_referencia` se informan pero no cuentan como fallo.

Los CFDI traen importes, no precios unitarios, asi que las referencias se
reproducen con totales (por ejemplo, energia = importe / kWh facturados) y se
guardan ya reducidas, sin datos de cliente.
"""
import json
import pathlib
import sys

DATA = pathlib.Path(__file__).resolve().parents[1] / "data" / "tarifas.json"


def desplazar(mes, n):
    """'2026-01' desplazado n meses -> '2025-12' con n = -1."""
    anio, m = (int(x) for x in mes.split("-"))
    total = anio * 12 + (m - 1) + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def aceptables(esperado):
    return list(esperado) if isinstance(esperado, (list, tuple)) else [esperado]


def validar(registros, ref, desfase=None):
    """Devuelve [{mes, mes_portal, cargo, esperado, obtenido, ok, motivo}], una fila por mes y cargo."""
    filas = []
    tol = ref.get("tolerancias", {})
    if desfase is None:
        desfase = ref.get("desfase_meses", 0)
    for mes in sorted(ref["meses"]):
        mes_portal = desplazar(mes, desfase)
        reg = registros.get(f"{ref['tarifa']}|{ref['region']}|{mes_portal}")
        for cargo, esperado in ref["meses"][mes].items():
            if reg is None:
                filas.append({"mes": mes, "mes_portal": mes_portal, "cargo": cargo, "esperado": esperado, "obtenido": None,
                              "ok": False, "motivo": "no hay registro capturado"})
                continue
            obtenido = reg["cargos"].get(cargo)
            if obtenido is None:
                filas.append({"mes": mes, "mes_portal": mes_portal, "cargo": cargo, "esperado": esperado, "obtenido": None,
                              "ok": False, "motivo": f"el registro no trae el cargo {cargo}"})
                continue
            t = tol.get(cargo, 0)
            # round: evita que 0.0020000001 de punto flotante falle una tolerancia de 0.002.
            ok = any(round(abs(obtenido - e), 6) <= t for e in aceptables(esperado))
            filas.append({"mes": mes, "mes_portal": mes_portal, "cargo": cargo, "esperado": esperado, "obtenido": obtenido,
                          "ok": ok, "motivo": "" if ok else f"fuera de tolerancia ({t})"})
    return filas


def main(argv):
    args = argv[1:]
    desfase = None
    if "--desfase" in args:
        i = args.index("--desfase")
        desfase = int(args[i + 1])
        del args[i:i + 2]
    if len(args) != 1:
        sys.exit("uso: python3 validar_referencia.py validacion/<archivo>.json [--desfase N]")
    ref = json.loads(pathlib.Path(args[0]).read_text(encoding="utf-8"))
    registros = json.loads(DATA.read_text(encoding="utf-8"))["registros"]
    filas = validar(registros, ref, desfase)
    usado = ref.get("desfase_meses", 0) if desfase is None else desfase
    print(f"{ref['tarifa']} {ref['region']}: tolerancias {ref.get('tolerancias')}, "
          f"desfase {usado} mes(es) (recibo -> portal)")
    for f in filas:
        marca = "ok   " if f["ok"] else "FALLA"
        print(f"  {marca} recibo {f['mes']} = portal {f['mes_portal']} {f['cargo']:<8} "
              f"esperado {f['esperado']}  obtenido {f['obtenido']}"
              + (f"  ({f['motivo']})" if f["motivo"] else ""))
    for mes, motivo in sorted(ref.get("sin_referencia", {}).items()):
        print(f"  --    {mes} sin referencia: {motivo}")
    malas = [f for f in filas if not f["ok"]]
    print(f"\n{len(filas) - len(malas)} de {len(filas)} comprobaciones correctas.")
    return 1 if malas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
