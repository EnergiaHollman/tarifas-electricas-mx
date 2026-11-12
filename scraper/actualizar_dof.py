"""Energía de GDMTO con 4 decimales, leída de los avisos del DOF.

No toca data/tarifas.json: escribe data/componentes_dof.json, una entrada por
mes y división que ya exista en tarifas.json:

    "GDMTO|ORIENTE|2025-09": {transmision, cenace, suministro, generacion,
                              energia_4dec, aviso_dof, fecha_captura}

Antes de guardar cada entrada se contrasta con lo capturado del portal:
distribución, capacidad y fijo deben coincidir exactos, y la energía del portal
debe ser la suma redondeada a 3 decimales (±0.0005). Si algo no cuadra, ese mes
NO se guarda y se reporta; el código sale con error.

También contrasta PDBT (fijo exacto y energía = suma de seis cargos, ±0.0005) y
escribe data/validacion.json: por registro, con qué se validó ("dof", "recibo"),
los huecos (meses sin captura del portal) y las diferencias sin explicar. Los
meses con recibo salen de scraper/validacion/recibos.json.

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
VALIDACION = RAIZ / "data" / "validacion.json"
RECIBOS = pathlib.Path(__file__).resolve().parent / "validacion" / "recibos.json"
TARIFAS_VALIDADAS = ("GDMTO", "PDBT")
# Domesticas con recibos: no pasan por el DOF (sus precios no salen del aviso mensual de
# suministro basico); se marcan solo con "recibo", por mes y temporada.
DOMESTICAS_CON_RECIBO = ("1E|NACIONAL", "1F|NACIONAL")
URL = "https://dof.gob.mx/nota_detalle_popup.php?codigo={codigo}"
# Ventana en la que las 17 divisiones de GDMTO y PDBT se capturaron y se esperan completas.
# Los huecos y el informe solo miran esta ventana; fuera de ella solo se valida lo que ya
# existe (p. ej. Noroeste y Oriente desde 2025-01).
VENTANA = ("2025-09", "2026-10")
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


# Qué se lee del aviso y qué se contrasta con el portal, por tarifa. «exactos» son
# cargos del portal que deben coincidir al centavo; la energía del portal debe ser
# la suma de los componentes por kWh redondeada (±0.0005).
CONFIG = {
    "GDMTO": {"fila": "gdmto", "suma": dof.energia_4dec, "exactos": ("distribucion", "capacidad", "fijo"),
              "componentes": ("transmision", "cenace", "suministro", "generacion")},
    "PDBT": {"fila": "pdbt", "suma": dof.energia_pdbt, "exactos": ("fijo",),
             "componentes": ("transmision", "distribucion", "cenace", "suministro", "generacion",
                             "capacidad")},
}


def construir(aviso, portal, codigo, ahora, tarifa="GDMTO"):
    """Entradas validadas de un aviso para una tarifa. Devuelve (entradas, problemas)."""
    cfg = CONFIG[tarifa]
    entradas, problemas = {}, []
    for clave, reg in portal.items():
        t, region, periodo = clave.split("|")
        if t != tarifa or periodo != f"{aviso['anio']}-{aviso['mes']:02d}":
            continue
        c = aviso[cfg["fila"]].get(region)
        if c is None:
            problemas.append(f"{clave}: el aviso no trae la división {region}.")
            continue
        cargos = reg["cargos"]
        suma = cfg["suma"](c)
        malos = [n for n in cfg["exactos"] if abs(float(c[n]) - cargos[n]) > 1e-9]
        if malos:
            problemas.append(f"{clave}: {', '.join(malos)} no coincide con el portal "
                             f"({[(float(c[n]), cargos[n]) for n in malos]}).")
        if abs(float(suma) - cargos["energia"]) > TOL_PORTAL:
            problemas.append(f"{clave}: energía del portal {cargos['energia']} vs suma del DOF {suma}.")
        if malos or abs(float(suma) - cargos["energia"]) > TOL_PORTAL:
            continue
        entradas[clave] = {**{n: float(c[n]) for n in cfg["componentes"]},
                           "energia_4dec": float(suma), "aviso_dof": codigo, "fecha_captura": ahora}
    return entradas, problemas


def anotar_validacion(portal, validados_dof, ventana_meses, regiones, recibos, ahora):
    """Arma data/validacion.json a partir de lo que cuadró con el DOF."""
    registros = {}
    for k in sorted(portal):
        t, region, periodo = k.split("|")
        if t not in TARIFAS_VALIDADAS:
            continue
        marcas = (["dof"] if k in validados_dof else [])
        r = recibos.get(f"{t}|{region}")
        if r and periodo in r["meses"]:
            marcas.append("recibo")
        if marcas:
            registros[k] = marcas
    bloques = {}
    for clave in DOMESTICAS_CON_RECIBO:
        r = recibos.get(clave)
        if not r:
            continue
        for periodo, temporada in sorted(r["temporada_por_mes"].items()):
            if f"{clave}|{periodo}" in portal:
                k = f"{clave}|{periodo}|{temporada}"
                registros[k] = ["recibo"]
                bloques[k] = ["basico"] + r.get("bloques_extra", {}).get(periodo, [])
    huecos = {}
    en_ventana = [m for m in ventana_meses if VENTANA[0] <= m <= VENTANA[1]]
    for t in TARIFAS_VALIDADAS:
        for region in regiones:
            for periodo in en_ventana:
                k = f"{t}|{region}|{periodo}"
                if k not in portal:
                    huecos[k] = "CFE no entregó la tabla de ese mes tras los reintentos; sin captura"
    return {"actualizado": ahora, "ventana": f"{VENTANA[0]}:{VENTANA[1]}",
            "registros": registros, "bloques_validados": bloques, "huecos": huecos}


def informe(validacion, portal, regiones, ventana_meses):
    """Tabla en markdown: por tarifa y división, cuántos meses hay y con qué se validó."""
    ventana_meses = [m for m in ventana_meses if VENTANA[0] <= m <= VENTANA[1]]
    n = len(ventana_meses)
    lineas = []
    for t in TARIFAS_VALIDADAS:
        lineas += [f"\n**{t}** ({n} meses por división)\n",
                   "| División | Capturados | Con DOF | Con recibo | Huecos |", "|---|---|---|---|---|"]
        for region in regiones:
            claves = [f"{t}|{region}|{p}" for p in ventana_meses]
            cap = sum(k in portal for k in claves)
            dof_ok = sum("dof" in validacion["registros"].get(k, []) for k in claves)
            rec = sum("recibo" in validacion["registros"].get(k, []) for k in claves)
            h = ", ".join(k.rsplit("|", 1)[1] for k in claves if k in validacion["huecos"]) or "—"
            lineas.append(f"| {region} | {cap}/{n} | {dof_ok} | {rec} | {h} |")
    return "\n".join(lineas)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--meses", nargs="+", help="AAAA-MM; por omisión, todos los avisos de avisos_dof.json")
    p.add_argument("--pausa", type=float, default=2.0, help="segundos entre descargas")
    p.add_argument("--informe", action="store_true", help="imprime la tabla de cobertura en markdown")
    a = p.parse_args(argv)

    portal = cargar(TARIFAS).get("registros", {})
    avisos = cargar(AVISOS)
    guardado = cargar(SALIDA)
    recibos = {k: v for k, v in cargar(RECIBOS).items() if not k.startswith("_")}
    ahora = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    pendientes = a.meses or sorted(avisos)
    problemas, nuevos = [], 0
    validados, regiones = set(), set()
    for periodo in pendientes:
        if periodo not in avisos:
            problemas.append(f"{periodo}: no hay código de aviso en data/avisos_dof.json.")
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
        regiones |= set(aviso["gdmto"])
        for tarifa in CONFIG:
            entradas, malos = construir(aviso, portal, avisos[periodo], ahora, tarifa=tarifa)
            problemas += malos
            validados |= set(entradas)
            for k, v in entradas.items():
                if k not in guardado or {x: y for x, y in guardado[k].items() if x != "fecha_captura"} \
                        != {x: y for x, y in v.items() if x != "fecha_captura"}:
                    guardado[k] = v
                    nuevos += 1

    SALIDA.write_text(json.dumps(guardado, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                      encoding="utf-8")
    ventana_meses = sorted(pendientes)
    validacion = anotar_validacion(portal, validados, ventana_meses, sorted(regiones), recibos, ahora)
    validacion["diferencias"] = sorted(problemas)
    if not a.meses:     # con --meses es una pasada parcial: no pisa el archivo completo
        VALIDACION.write_text(json.dumps(validacion, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                              encoding="utf-8")
    print(f"{nuevos} entradas nuevas o cambiadas; {len(guardado)} en total.")
    print(f"validados con DOF: {len(validados)}; huecos: {len(validacion['huecos'])}")
    if a.informe:
        print(informe(validacion, portal, sorted(regiones), ventana_meses))
    for m in problemas:
        print("SOSPECHOSO:", m)
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
