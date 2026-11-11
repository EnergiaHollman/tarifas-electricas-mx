"""Energía de GDMTO con 4 decimales, leída de los avisos del DOF.

No toca data/tarifas.json: escribe data/componentes_dof.json, una entrada por
mes y división que ya exista en tarifas.json:

    "GDMTO|ORIENTE|2025-09": {transmision, cenace, suministro, generacion,
                              energia_4dec, aviso_dof, fecha_captura}

Antes de guardar cada entrada se contrasta con lo capturado del portal:
distribución, capacidad y fijo deben coincidir exactos, y la energía del portal
debe ser la suma redondeada a 3 decimales (±0.0005). Si algo no cuadra, ese mes
NO se guarda y se reporta; el código sale con error.

Los avisos se listan a mano en data/avisos_dof.json ({"AAAA-MM": codigo_dof}):
el DOF no ofrece una lista consultable y cada mes sale con 10 a 25 días de
retraso.

    python3 actualizar_dof.py                  # los avisos que falten
    python3 actualizar_dof.py --meses 2026-05  # uno en concreto
"""
import argparse
import datetime
import json
import pathlib
import sys
import time

import requests

import dof

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TARIFAS = RAIZ / "data" / "tarifas.json"
AVISOS = RAIZ / "data" / "avisos_dof.json"
SALIDA = RAIZ / "data" / "componentes_dof.json"
URL = "https://dof.gob.mx/nota_detalle_popup.php?codigo={codigo}"
TARIFA = "GDMTO"
TOL_PORTAL = 0.0005 + 1e-9


def cargar(ruta):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def descargar(codigo, pausa):
    time.sleep(pausa)
    r = requests.get(URL.format(codigo=codigo), timeout=60,
                     headers={"User-Agent": "tarifas-electricas-mx (lectura mensual de avisos del DOF)"})
    r.raise_for_status()
    # Las páginas del DOF traen acentos como entidades; latin-1 no pierde bytes.
    return r.content.decode("latin-1")


def construir(aviso, portal, codigo, ahora):
    """Entradas validadas de un aviso. Devuelve (entradas, problemas)."""
    entradas, problemas = {}, []
    for clave, reg in portal.items():
        t, region, periodo = clave.split("|")
        if t != TARIFA or periodo != f"{aviso['anio']}-{aviso['mes']:02d}":
            continue
        c = aviso["gdmto"].get(region)
        if c is None:
            problemas.append(f"{clave}: el aviso no trae la división {region}.")
            continue
        cargos = reg["cargos"]
        suma = dof.energia_4dec(c)
        malos = [n for n in ("distribucion", "capacidad", "fijo")
                 if abs(float(c[n]) - cargos[n]) > 1e-9]
        if malos:
            problemas.append(f"{clave}: {', '.join(malos)} no coincide con el portal "
                             f"({[(float(c[n]), cargos[n]) for n in malos]}).")
        if abs(float(suma) - cargos["energia"]) > TOL_PORTAL:
            problemas.append(f"{clave}: portal {cargos['energia']} vs suma del DOF {suma}.")
        if malos or abs(float(suma) - cargos["energia"]) > TOL_PORTAL:
            continue
        entradas[clave] = {
            "transmision": float(c["transmision"]), "cenace": float(c["cenace"]),
            "suministro": float(c["suministro"]), "generacion": float(c["generacion"]),
            "energia_4dec": float(suma), "aviso_dof": codigo, "fecha_captura": ahora,
        }
    return entradas, problemas


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--meses", nargs="+", help="AAAA-MM; por omisión, los avisos que falten")
    p.add_argument("--pausa", type=float, default=2.0, help="segundos entre descargas")
    a = p.parse_args(argv)

    portal = cargar(TARIFAS).get("registros", {})
    avisos = cargar(AVISOS)
    guardado = cargar(SALIDA)
    ahora = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    pendientes = a.meses or sorted(avisos)
    problemas, nuevos = [], 0
    for periodo in pendientes:
        if periodo not in avisos:
            problemas.append(f"{periodo}: no hay código de aviso en data/avisos_dof.json.")
            continue
        esperadas = [k for k in portal if k.startswith(TARIFA + "|") and k.endswith("|" + periodo)]
        if not a.meses and all(k in guardado for k in esperadas):
            continue
        try:
            aviso = dof.parsear_aviso(descargar(avisos[periodo], a.pausa))
        except (dof.ErrorDOF, requests.RequestException) as e:
            problemas.append(f"{periodo}: {e}")
            continue
        if f"{aviso['anio']}-{aviso['mes']:02d}" != periodo:
            problemas.append(f"{periodo}: el aviso {avisos[periodo]} es de "
                             f"{aviso['anio']}-{aviso['mes']:02d}.")
            continue
        entradas, malos = construir(aviso, portal, avisos[periodo], ahora)
        problemas += malos
        for k, v in entradas.items():
            if k not in guardado or {x: y for x, y in guardado[k].items() if x != "fecha_captura"} \
                    != {x: y for x, y in v.items() if x != "fecha_captura"}:
                guardado[k] = v
                nuevos += 1

    SALIDA.write_text(json.dumps(guardado, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(f"{nuevos} entradas nuevas o cambiadas; {len(guardado)} en total.")
    for m in problemas:
        print("SOSPECHOSO:", m)
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
