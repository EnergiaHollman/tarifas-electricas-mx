"""Busca en el índice diario del DOF el aviso de tarifas finales de un mes.

No escribe nada: ni data/avisos_dof.json ni ningún otro archivo. Imprime el
código del aviso y la línea para agregarlo a mano. Después:

    python3 actualizar_dof.py --meses AAAA-MM      # (con el código ya agregado)

El DOF publica el aviso de «Tarifas Finales del Suministro Básico ... a partir
del 1 de <mes> de <año>» hacia el final de ese mes (el de septiembre de 2026
salió el 30 de septiembre). El índice de cada día lista el título completo, así
que no hace falta abrir las notas.

    python3 buscar_aviso_dof.py --mes 2026-11
    python3 buscar_aviso_dof.py --mes 2026-11 --desde 2026-11-20 --hasta 2026-11-30

Por omisión recorre del día 15 del mes anterior al día 15 del mes siguiente,
sin pasar de hoy, con 2 s entre peticiones (unas 60 como máximo).

Códigos de salida:
    0  encontrado (se imprime el código)
    1  no encontrado, y todos los días del rango se leyeron: todavía no sale
    2  no se pudo concluir: algún día no se pudo leer (se dice cuáles)
"""
import argparse
import datetime
import html
import re
import sys
import time

import requests

import dof

URL = "https://dof.gob.mx/index_111.php?year={y}&month={m:02d}&day={d:02d}"
_ANCLA = re.compile(r'<a[^>]+href="[^"]*codigo=(\d+)[^"]*"[^>]*>(.*?)</a>', re.S | re.I)
_TITULO = re.compile(r"tarifas finales del suministro b[aá]sico", re.I)
_MES = re.compile(r"a partir del 1 de (\w+) de (\d{4})", re.I)
AGENTE = "tarifas-electricas-mx (busqueda manual del aviso mensual en el indice del DOF)"


def titulos_del_dia(crudo: str):
    """[(codigo, titulo)] de las notas del índice, sin repetir códigos."""
    vistos, salida = set(), []
    for codigo, interior in _ANCLA.findall(crudo):
        titulo = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", interior))).strip()
        if titulo and codigo not in vistos:
            vistos.add(codigo)
            salida.append((codigo, titulo))
    return salida


def periodo_del_titulo(titulo: str):
    """'AAAA-MM' si es un aviso de tarifas finales del Suministro Básico; si no, None."""
    if not _TITULO.search(titulo):
        return None
    m = _MES.search(titulo)
    if not m or m.group(1).lower() not in dof.MESES:
        return None
    return f"{int(m.group(2))}-{dof.MESES.index(m.group(1).lower()) + 1:02d}"


def rango_por_omision(periodo: str, hoy: datetime.date):
    a, m = int(periodo[:4]), int(periodo[5:])
    ant = datetime.date(a, m, 1) - datetime.timedelta(days=1)
    desde = ant.replace(day=15)
    sig = (datetime.date(a, m, 28) + datetime.timedelta(days=4)).replace(day=15)
    return desde, min(sig, hoy)


def dias(desde: datetime.date, hasta: datetime.date):
    d = desde
    while d <= hasta:
        yield d
        d += datetime.timedelta(days=1)


def leer_indice(dia: datetime.date, intentos=2, pausa=2.0, dormir=time.sleep):
    """HTML del índice del día. Reintenta una vez; si falla, levanta requests.RequestException."""
    ultimo = None
    for i in range(intentos):
        try:
            r = requests.get(URL.format(y=dia.year, m=dia.month, d=dia.day), timeout=40,
                             headers={"User-Agent": AGENTE})
            r.raise_for_status()
            return r.content.decode("latin-1")
        except requests.RequestException as e:
            ultimo = e
            if i + 1 < intentos:
                dormir(pausa * 2)
    raise ultimo


def buscar(periodo, desde, hasta, leer=leer_indice, pausa=2.0, dormir=time.sleep, avisar=lambda s: None):
    """Recorre los días. Devuelve (hallazgos, dias_sin_leer, dias_revisados).

    hallazgos = [(dia, codigo, titulo)]. Se detiene en el primero: un aviso
    del mismo mes que se republique después no se busca.
    """
    hallazgos, sin_leer, revisados = [], [], 0
    for dia in dias(desde, hasta):
        if revisados or sin_leer:
            dormir(pausa)
        try:
            crudo = leer(dia)
        except requests.RequestException as e:
            sin_leer.append((dia, str(e)))
            avisar(f"  {dia}  no se pudo leer: {e}")
            continue
        revisados += 1
        for codigo, titulo in titulos_del_dia(crudo):
            if periodo_del_titulo(titulo) == periodo:
                hallazgos.append((dia, codigo, titulo))
                avisar(f"  {dia}  {codigo}  {titulo[:70]}…")
        if hallazgos:
            break
    return hallazgos, sin_leer, revisados


def main(argv=None, leer=leer_indice, hoy=None, dormir=time.sleep):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--mes", required=True, metavar="AAAA-MM", help="mes cuyas tarifas se buscan")
    p.add_argument("--desde", help="AAAA-MM-DD; por omisión el día 15 del mes anterior")
    p.add_argument("--hasta", help="AAAA-MM-DD; por omisión el día 15 del mes siguiente, sin pasar de hoy")
    p.add_argument("--pausa", type=float, default=2.0, help="segundos entre peticiones")
    a = p.parse_args(argv)

    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", a.mes):
        print(f"--mes debe ser AAAA-MM; llegó {a.mes!r}")
        return 2
    hoy = hoy or datetime.date.today()
    try:
        d0, d1 = rango_por_omision(a.mes, hoy)
        if a.desde:
            d0 = datetime.date.fromisoformat(a.desde)
        if a.hasta:
            d1 = min(datetime.date.fromisoformat(a.hasta), hoy)
    except ValueError as e:
        print(f"fecha inválida: {e}")
        return 2
    if d0 > d1:
        print(f"Rango vacío ({d0} a {d1}): todavía no hay días que revisar para {a.mes}.")
        return 1

    print(f"Buscando el aviso de {a.mes} en el índice del DOF, del {d0} al {d1}.")
    hallazgos, sin_leer, revisados = buscar(a.mes, d0, d1, leer=leer, pausa=a.pausa,
                                            dormir=dormir, avisar=print)
    if hallazgos:
        dia, codigo, titulo = hallazgos[0]
        print(f"\nEncontrado: aviso de {a.mes}, publicado el {dia}, código {codigo}.")
        print(f"  https://dof.gob.mx/nota_detalle_popup.php?codigo={codigo}")
        print(f'Para usarlo, agrega a data/avisos_dof.json:   "{a.mes}": {codigo}')
        print(f"y corre:  python3 actualizar_dof.py --meses {a.mes}")
        print("(Este script no escribió nada.)")
        return 0
    if sin_leer:
        print(f"\nNo se pudo concluir: {len(sin_leer)} día(s) no se pudieron leer, "
              f"{revisados} sí. Días sin leer: {', '.join(str(d) for d, _ in sin_leer)}.")
        print("Vuelve a correrlo (puedes acotar con --desde y --hasta). No se escribió nada.")
        return 2
    print(f"\nNo encontrado: se revisaron los {revisados} días del {d0} al {d1} y ninguno trae "
          f"el aviso de {a.mes}. Todavía no sale, o salió fuera de ese rango (prueba --hasta). "
          "No se escribió nada.")
    return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)    # que el avance se vea mientras corre
    sys.exit(main())
