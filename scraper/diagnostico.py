# -*- coding: utf-8 -*-
"""Compara dos órdenes de selección para ver cuál deja el sitio usable.

El backfill selecciona estado, municipio y región ANTES de tocar el año. Esto
reproduce exactamente ese orden (el "bueno") y, aparte, el orden que sí
rompió en una corrida anterior (año antes de región), para confirmar si el
problema real está en el primero o solo en el segundo.

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
    m_sel = s._actual(P.DD_MES)
    r_sel = s._actual(P.DD_REGION)
    print(f"\n--- {etiqueta}")
    print(f"    año: {a_sel[1]}   ofrecidos: {anios}")
    print(f"    mes: {m_sel[1]}   ofrecidos: {meses}")
    print(f"    región: {r_sel[1]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estado", default="SONORA")
    ap.add_argument("--municipio", default="NAVOJOA")
    ap.add_argument("--anio", type=int, default=2019)
    ap.add_argument("--pausa", type=float, default=1.5)
    ap.add_argument("--inseguro", action="store_true")
    args = ap.parse_args()

    def resolver_ids(s):
        eid = next((v for v, t in s.estados() if P.normalizar(t) == P.normalizar(args.estado)), None)
        if eid is None:
            raise SystemExit(f"estado no encontrado: {args.estado}")
        s.poner_estado(eid)
        mid = next((v for v, t in s.municipios() if P.normalizar(t) == P.normalizar(args.municipio)), None)
        if mid is None:
            raise SystemExit(f"municipio no encontrado: {args.municipio}")
        return eid, mid

    print("=" * 70)
    print("ORDEN DE PRODUCCIÓN: estado, municipio, región, luego año y mes")
    print("=" * 70)
    s = cfe.SesionCFE("GDMTH", pausa=args.pausa, verificar_tls=not args.inseguro).abrir()
    eid, mid = resolver_ids(s)
    s.poner_municipio(mid)
    rid, rnombre = s._actual(P.DD_REGION)
    if rid is None:
        opciones = s.regiones_disponibles()
        if opciones:
            rid, rnombre = opciones[0]
            s.poner_region(rid)
    estado_actual(s, f"región puesta ({rnombre})")

    try:
        s.poner_anio(args.anio)
        estado_actual(s, f"tras elegir año {args.anio}")
        meses = s.meses()
        if not meses:
            print(f"    !! el año {args.anio} se seleccionó pero no ofrece meses")
        else:
            s.poner_mes(meses[0])
            estado_actual(s, f"tras elegir mes {meses[0]}")
            r = P.parsear_cargos(s.html)
            print(f"    resultado: {r['cargos'] if r else None}")
        print("\n>>> ORDEN DE PRODUCCIÓN: SIN ERRORES")
    except cfe.ErrorCFE as e:
        print(f"\n>>> ORDEN DE PRODUCCIÓN FALLÓ: {e}")

    print("\n" + "=" * 70)
    print("HIPÓTESIS: fijar un mes antes de cambiar de año")
    print("=" * 70)
    s3 = cfe.SesionCFE("GDMTH", pausa=args.pausa, verificar_tls=not args.inseguro).abrir()
    eid3, mid3 = resolver_ids(s3)
    s3.poner_municipio(mid3)
    rid3, rnombre3 = s3._actual(P.DD_REGION)
    if rid3 is None:
        opciones3 = s3.regiones_disponibles()
        if opciones3:
            rid3, rnombre3 = opciones3[0]
            s3.poner_region(rid3)
    estado_actual(s3, f"región puesta ({rnombre3})")
    meses_antes = s3.meses()
    if meses_antes:
        s3.poner_mes(meses_antes[0])
        estado_actual(s3, f"mes {meses_antes[0]} fijado, antes de tocar el año")
    try:
        s3.poner_anio(args.anio)
        estado_actual(s3, f"tras elegir año {args.anio} (con mes ya fijado)")
        meses3 = s3.meses()
        if meses3:
            s3.poner_mes(meses3[0])
            estado_actual(s3, f"tras elegir mes {meses3[0]}")
            r3 = P.parsear_cargos(s3.html)
            print(f"    resultado: {r3['cargos'] if r3 else None}")
            print("\n>>> HIPÓTESIS CONFIRMADA: fijar el mes antes lo resuelve")
        else:
            print("\n>>> HIPÓTESIS DESCARTADA: sigue sin ofrecer meses")
    except cfe.ErrorCFE as e:
        print(f"\n>>> HIPÓTESIS FALLÓ: {e}")

    print("\n" + "=" * 70)
    print("ORDEN QUE YA SABEMOS QUE FALLA: año antes de región (control)")
    print("=" * 70)
    s2 = cfe.SesionCFE("GDMTH", pausa=args.pausa, verificar_tls=not args.inseguro).abrir()
    eid2, mid2 = resolver_ids(s2)
    s2.poner_municipio(mid2)
    try:
        s2.poner_anio(args.anio)
        estado_actual(s2, f"año {args.anio} sin región")
        meses2 = s2.meses()
        if meses2:
            s2.poner_mes(meses2[0])
        else:
            print("    meses vacíos, como en la corrida anterior; se detiene aquí a propósito")
        print("\n>>> ORDEN DE CONTROL: SIN ERRORES (inesperado)")
    except cfe.ErrorCFE as e:
        print(f"\n>>> ORDEN DE CONTROL FALLÓ (esperado): {e}")


if __name__ == "__main__":
    main()
