# -*- coding: utf-8 -*-
"""Prueba en vivo el flujo completo para un año pasado, con el control de mes
correcto (ver parser.control_mes: el nombre del control cambia según si el
año es el actual o uno pasado).

    python3 diagnostico.py                       # Navojoa, Sonora, 2019
    python3 diagnostico.py --estado SONORA --municipio NAVOJOA --anio 2019
"""
import argparse

import cfe
import parser as P


def estado_actual(s, etiqueta):
    anios = s.anios()
    meses = s.meses()
    a_sel = s._actual(P.DD_ANIO)
    m_sel = s._actual(P.DD_MES)     # se resuelve solo al control que exista
    r_sel = s._actual(P.DD_REGION)
    print(f"\n--- {etiqueta}")
    print(f"    año: {a_sel[1]}   ofrecidos: {anios}")
    print(f"    mes: {m_sel[1]}   ofrecidos: {meses}   "
          f"(control: {P.control_mes(s.html)})")
    print(f"    región: {r_sel[1]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estado", default="SONORA")
    ap.add_argument("--municipio", default="NAVOJOA")
    ap.add_argument("--anio", type=int, default=2019)
    ap.add_argument("--pausa", type=float, default=1.5)
    ap.add_argument("--inseguro", action="store_true")
    ap.add_argument("--cookies", default=None,
                    help="ya no debería hacer falta; se deja por si acaso")
    args = ap.parse_args()

    s = cfe.SesionCFE("GDMTH", pausa=args.pausa, verificar_tls=not args.inseguro,
                      cookies=args.cookies).abrir()
    estado_actual(s, "página recién cargada")

    eid = next((v for v, t in s.estados() if P.normalizar(t) == P.normalizar(args.estado)), None)
    if eid is None:
        raise SystemExit(f"estado no encontrado: {args.estado}")
    s.poner_estado(eid)
    mid = next((v for v, t in s.municipios() if P.normalizar(t) == P.normalizar(args.municipio)), None)
    if mid is None:
        raise SystemExit(f"municipio no encontrado: {args.municipio}")
    s.poner_municipio(mid)
    estado_actual(s, f"ubicación puesta ({args.estado}, {args.municipio})")

    s.poner_anio(args.anio)
    estado_actual(s, f"año {args.anio} elegido")

    meses = s.meses()
    if not meses:
        print(f"\n>>> el año {args.anio} no ofrece meses; algo más está mal")
        return

    s.poner_mes(meses[0])
    estado_actual(s, f"mes {meses[0]} elegido")

    r = P.parsear_cargos(s.html)
    if r and r["cargos"]:
        print(f"\n>>> FUNCIONA: {r['region']} {r['periodo_cfe']}  {r['cargos']}")
    else:
        print("\n>>> la página respondió pero sin cargos reconocibles")


if __name__ == "__main__":
    main()
