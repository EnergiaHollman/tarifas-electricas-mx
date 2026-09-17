# -*- coding: utf-8 -*-
"""Construye data/catalogo.json: estado -> municipio -> región tarifaria.

Este mapeo casi nunca cambia, así que se corre una vez y se olvida. Es la
parte cara: hace un postback por municipio (~2,400 en todo el país, cerca de
una hora con la pausa por omisión).

Es reanudable: guarda después de cada estado y omite lo que ya está. Si se
corta, vuelve a correrlo.

    python3 construir_catalogo.py --estados SONORA SINALOA
    python3 construir_catalogo.py                 # todo el país
    python3 construir_catalogo.py --rehacer       # ignora lo ya guardado
"""
import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

import cfe
import parser as P

DATA = pathlib.Path(__file__).resolve().parents[1] / "data"
DESTINO = DATA / "catalogo.json"


def cargar():
    if DESTINO.exists():
        return json.loads(DESTINO.read_text(encoding="utf-8"))
    return {"generado": None, "fuente": cfe.PAGINAS["GDMTH"], "estados": {}}


def guardar(cat):
    cat["generado"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    DATA.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(cat, ensure_ascii=False, indent=1, sort_keys=True),
                       encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estados", nargs="*", help="nombres de estado; omitir = todos")
    ap.add_argument("--rehacer", action="store_true")
    ap.add_argument("--pausa", type=float, default=1.5)
    ap.add_argument("--inseguro", action="store_true",
                    help="salta la verificación TLS; último recurso")
    args = ap.parse_args()

    cat = {"generado": None, "fuente": cfe.PAGINAS["GDMTH"], "estados": {}} if args.rehacer else cargar()

    s = cfe.SesionCFE("GDMTH", pausa=args.pausa, verificar_tls=not args.inseguro).abrir()
    estados = s.estados()
    if args.estados:
        querer = {P.normalizar(e) for e in args.estados}
        estados = [(v, t) for v, t in estados if P.normalizar(t) in querer]
        if not estados:
            sys.exit("ningún estado coincide; nombres válidos: " +
                     ", ".join(t for _, t in s.estados()))

    for i, (eid, estado) in enumerate(estados, 1):
        clave = P.normalizar(estado)
        previo = cat["estados"].get(clave, {})
        print(f"[{i}/{len(estados)}] {estado}")
        s.poner_estado(eid)
        municipios = s.municipios()
        entrada = {"id": eid, "nombre": estado,
                   "municipios": previo.get("municipios", {})}

        for j, (mid, municipio) in enumerate(municipios, 1):
            k = P.normalizar(municipio)
            if k in entrada["municipios"] and not args.rehacer:
                continue
            rid, region = s.region_de_municipio(eid, mid)
            if region is None:
                print(f"    ! sin región: {municipio}")
                continue
            entrada["municipios"][k] = {"id": mid, "nombre": municipio,
                                        "region": P.normalizar(region),
                                        "region_id": rid}
            print(f"    {j}/{len(municipios)} {municipio} -> {region}")

        cat["estados"][clave] = entrada
        guardar(cat)          # se guarda estado por estado: reanudable

    regiones = sorted({m["region"] for e in cat["estados"].values()
                       for m in e["municipios"].values()})
    print(f"\nListo. {len(cat['estados'])} estado(s), "
          f"{sum(len(e['municipios']) for e in cat['estados'].values())} municipios, "
          f"{len(regiones)} región(es): {', '.join(regiones)}")


if __name__ == "__main__":
    main()
