# -*- coding: utf-8 -*-
"""Captura cargos y horarios y los escribe en data/.

Los cargos dependen de la región tarifaria, no del municipio, así que basta
un municipio representativo por región: son ~8 consultas por mes en vez de
2,400. El representativo sale del catálogo.

    # backfill de una región
    python3 actualizar_tarifas.py --regiones NOROESTE --desde 2024

    # backfill completo (tarda; hazlo una vez)
    python3 actualizar_tarifas.py --desde 2017

    # lo que corre el cron mensual: solo lo que falte
    python3 actualizar_tarifas.py --faltantes

Nunca reescribe un registro ya capturado salvo con --rehacer: un mes cerrado
no cambia, y si cambia quieres enterarte, no que se sobreescriba callado.
"""
import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

import cfe
import parser as P

DATA = pathlib.Path(__file__).resolve().parents[1] / "data"
CATALOGO = DATA / "catalogo.json"
TARIFAS = DATA / "tarifas.json"
HORARIOS = DATA / "horarios.json"


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cargar(ruta, vacio):
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    return vacio


def escribir(ruta, datos):
    DATA.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True),
                    encoding="utf-8")


def representantes(catalogo):
    """{REGION: (estado_id, municipio_id, etiqueta)} tomando el primer municipio."""
    fuera = {}
    for estado in catalogo.get("estados", {}).values():
        for municipio in estado["municipios"].values():
            fuera.setdefault(municipio["region"],
                             (estado["id"], municipio["id"],
                              f"{municipio['nombre']}, {estado['nombre']}"))
    return fuera


def clave(tarifa, region, anio, mes):
    return f"{tarifa}|{region}|{anio:04d}-{mes:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tarifa", default="GDMTH", choices=sorted(cfe.PAGINAS))
    ap.add_argument("--regiones", nargs="*", help="omitir = todas las del catálogo")
    ap.add_argument("--desde", type=int, help="año inicial")
    ap.add_argument("--hasta", type=int, help="año final")
    ap.add_argument("--faltantes", action="store_true",
                    help="solo lo que no esté capturado (modo cron)")
    ap.add_argument("--rehacer", action="store_true")
    ap.add_argument("--pausa", type=float, default=1.5)
    ap.add_argument("--inseguro", action="store_true",
                    help="salta la verificación TLS; último recurso")
    args = ap.parse_args()

    catalogo = cargar(CATALOGO, None)
    if not catalogo:
        sys.exit("falta data/catalogo.json: corre construir_catalogo.py primero")

    reps = representantes(catalogo)
    if args.regiones:
        querer = {P.normalizar(r) for r in args.regiones}
        faltan = querer - set(reps)
        if faltan:
            sys.exit(f"no hay municipios en el catálogo para: {', '.join(sorted(faltan))}")
        reps = {k: v for k, v in reps.items() if k in querer}
    if not reps:
        sys.exit("el catálogo no tiene regiones")

    tarifas = cargar(TARIFAS, {"actualizado": None, "fuente": cfe.PAGINAS[args.tarifa],
                               "registros": {}})
    registros = tarifas["registros"]

    s = cfe.SesionCFE(args.tarifa, pausa=args.pausa, verificar_tls=not args.inseguro).abrir()

    # Los horarios vienen en cualquier respuesta de la página.
    escribir(HORARIOS, {"generado": ahora(), "fuente": s.url, "zonas": s.horarios()})
    print(f"horarios -> {HORARIOS.name}")

    disponibles = sorted(s.anios(), reverse=True)
    desde = args.desde or max(disponibles)
    hasta = args.hasta or max(disponibles)
    anios = [a for a in sorted(disponibles) if desde <= a <= hasta]
    if not anios:
        sys.exit(f"años disponibles en CFE: {min(disponibles)}–{max(disponibles)}")

    nuevos = omitidos = vacios = 0
    for region, (eid, mid, etiqueta) in sorted(reps.items()):
        print(f"\n== {region}  ({etiqueta})")
        s.poner_estado(eid)
        s.poner_municipio(mid)
        for anio in anios:
            s.poner_anio(anio)
            for mes in s.meses():          # CFE solo lista los meses publicados
                k = clave(args.tarifa, region, anio, mes)
                if k in registros and not args.rehacer:
                    omitidos += 1
                    continue
                if args.faltantes and k in registros:
                    omitidos += 1
                    continue
                r = s.consultar(anio, mes, eid, mid)
                if r is None or not r["cargos"]:
                    print(f"   {anio}-{mes:02d}  sin publicación")
                    vacios += 1
                    continue
                if P.normalizar(r["region"] or "") != region:
                    print(f"   {anio}-{mes:02d}  ! la página respondió "
                          f"{r['region']!r}, se esperaba {region}; se omite")
                    continue
                registros[k] = {
                    "tarifa": args.tarifa, "region": region,
                    "anio": anio, "mes": mes,
                    "periodo_cfe": r["periodo_cfe"],
                    "cargos": r["cargos"], "unidades": r["unidades"],
                    "conceptos": r["conceptos"],
                    "municipio_consultado": etiqueta,
                    "fuente": s.url, "fecha_captura": ahora(),
                }
                nuevos += 1
                print(f"   {anio}-{mes:02d}  " +
                      "  ".join(f"{k2}={v}" for k2, v in r["cargos"].items()))
                tarifas["actualizado"] = ahora()
                escribir(TARIFAS, tarifas)   # guardado incremental: reanudable

    tarifas["actualizado"] = ahora()
    escribir(TARIFAS, tarifas)
    print(f"\n{nuevos} nuevo(s), {omitidos} ya estaban, {vacios} sin publicación. "
          f"Total en base: {len(registros)}")
    if nuevos == 0 and not omitidos:
        sys.exit(2)      # el cron lo marca como falla: algo cambió en CFE


if __name__ == "__main__":
    main()
