# -*- coding: utf-8 -*-
"""Inspecciona qué ofrece el sitio de CFE en cada paso de la secuencia.

Sirve para ver por qué un año no se puede recorrer. Imprime, tras cada
postback, qué años y qué meses quedan disponibles y qué quedó seleccionado.

    python3 diagnostico.py                       # Navojoa, Sonora
    python3 diagnostico.py --estado SONORA --municipio NAVOJOA --anio 2019

Es de lectura: no escribe nada en data/.
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
    tablas = P.parsear_todas(s.html)
    print(f"\n--- {etiqueta}")
    print(f"    año seleccionado : {a_sel[1]}")
    print(f"    años ofrecidos   : {anios}")
    print(f"    mes seleccionado : {m_sel[1]}")
    print(f"    meses ofrecidos  : {meses}")
    print(f"    región           : {r_sel[1]}")
    print(f"    tablas con datos : {sum(1 for t in tablas if t['cargos'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estado", default="SONORA")
    ap.add_argument("--municipio", default="NAVOJOA")
    ap.add_argument("--anio", type=int, default=2019)
    ap.add_argument("--mes", type=int, default=6)
    ap.add_argument("--pausa", type=float, default=1.5)
    ap.add_argument("--inseguro", action="store_true")
    args = ap.parse_args()

    s = cfe.SesionCFE("GDMTH", pausa=args.pausa,
                      verificar_tls=not args.inseguro).abrir()
    estado_actual(s, "al cargar la página")

    eid = next((v for v, t in s.estados() if P.normalizar(t) == P.normalizar(args.estado)), None)
    if eid is None:
        raise SystemExit(f"estado no encontrado: {args.estado}")
    s.poner_estado(eid)
    estado_actual(s, f"tras elegir estado {args.estado}")

    mid = next((v for v, t in s.municipios() if P.normalizar(t) == P.normalizar(args.municipio)), None)
    if mid is None:
        raise SystemExit(f"municipio no encontrado: {args.municipio}")
    s.poner_municipio(mid)
    estado_actual(s, f"tras elegir municipio {args.municipio}")

    s.poner_anio(args.anio)
    estado_actual(s, f"tras elegir año {args.anio}")

    s.poner_mes(args.mes)
    estado_actual(s, f"tras elegir mes {args.mes}")

    for t in P.parsear_todas(s.html):
        print(f"\n    tabla: region={t['region']!r} periodo={t['periodo_cfe']!r}")
        print(f"           cargos={t['cargos']}")

    # El orden inverso también importa: así lo hace el scraper al recorrer.
    print("\n=== ahora al revés: año y mes primero, ubicación después ===")
    s2 = cfe.SesionCFE("GDMTH", pausa=args.pausa,
                       verificar_tls=not args.inseguro).abrir()
    s2.poner_anio(args.anio)
    estado_actual(s2, f"año {args.anio} sin ubicación")
    s2.poner_mes(args.mes)
    estado_actual(s2, f"mes {args.mes} sin ubicación")
    s2.poner_estado(eid)
    s2.poner_municipio(mid)
    estado_actual(s2, "ubicación puesta al final")


if __name__ == "__main__":
    main()
