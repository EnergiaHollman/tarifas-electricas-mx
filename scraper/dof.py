"""Avisos mensuales de tarifas finales del Suministro Básico (DOF).

El portal de CFE muestra la energía de GDMTO con 3 decimales: es la suma de
cuatro cargos por kWh del aviso del DOF, redondeada. El aviso trae esos cuatro
cargos por separado (tres con 4 decimales), así que su suma conserva la
precisión que el portal pierde.

Fila de GDMTO en cada división (texto sin etiquetas):
    GDMTO $/kWh <transmisión> <CENACE> <suministradora> <generación>
          $/kW <distribución> <capacidad> $/mes <fijo>
"""
import html
import re
from decimal import Decimal

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

_N = r"(\d+(?:\.\d+)?)"
_FILA_GDMTO = re.compile(
    r"GDMTO \$/kWh " + _N + " " + _N + " " + _N + " " + _N
    + r" \$/kW " + _N + " " + _N + r" \$/mes " + _N)
_DIVISION = re.compile(r"División ([^\d$]+?) Categor")


class ErrorDOF(ValueError):
    """El aviso no tiene la forma esperada: mejor no guardar nada."""


def _texto(crudo: str) -> str:
    t = re.sub(r"<style.*?</style>|<script.*?</script>", "", crudo, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t)


def clave_region(nombre: str) -> str:
    """'Bajío' -> 'BAJIO', 'Valle de México Norte' -> 'VALLE DE MEXICO NORTE'."""
    t = nombre.strip().upper()
    for a, b in zip("ÁÉÍÓÚÑ", "AEIOUN"):
        t = t.replace(a, b)
    return t


def parsear_aviso(crudo: str) -> dict:
    """Devuelve {anio, mes, gdmto: {REGION: {...}}} con los cargos de GDMTO.

    Los números se devuelven como Decimal: la suma de cuatro floats arrastraría
    ruido binario justo en el cuarto decimal que se quiere conservar.
    """
    t = _texto(crudo)
    m = re.search(r"a partir del 1 de (\w+) de (\d{4})", t)
    if not m or m.group(1) not in MESES:
        raise ErrorDOF("No se encontró «a partir del 1 de <mes> de <año>» en el aviso.")
    anio, mes = int(m.group(2)), MESES.index(m.group(1)) + 1

    cortes = [(d.start(), d.group(1)) for d in _DIVISION.finditer(t)]
    if not cortes:
        raise ErrorDOF("El aviso no trae divisiones.")
    gdmto = {}
    for i, (ini, nombre) in enumerate(cortes):
        fin = cortes[i + 1][0] if i + 1 < len(cortes) else len(t)
        f = _FILA_GDMTO.search(t[ini:fin])
        if not f:
            raise ErrorDOF(f"Sin fila de GDMTO reconocible en la división {nombre}.")
        v = [Decimal(x) for x in f.groups()]
        clave = clave_region(nombre)
        if clave in gdmto:
            raise ErrorDOF(f"División repetida en el aviso: {nombre}.")
        gdmto[clave] = {
            "transmision": v[0], "cenace": v[1], "suministro": v[2], "generacion": v[3],
            "distribucion": v[4], "capacidad": v[5], "fijo": v[6],
        }
    return {"anio": anio, "mes": mes, "gdmto": gdmto}


def energia_4dec(c: dict) -> Decimal:
    """Suma de los cuatro cargos por kWh, sin redondear más allá del 4.º decimal."""
    return c["transmision"] + c["cenace"] + c["suministro"] + c["generacion"]
