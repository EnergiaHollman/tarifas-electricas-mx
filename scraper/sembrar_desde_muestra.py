# -*- coding: utf-8 -*-
"""Siembra data/ a partir del HTML de muestra, sin tocar la red.

Sirve para que el Worker arranque con datos reales el primer día y para
probar la API antes de correr el scraper. Lo que siembra:

  - horarios.json  completo (la página los trae siempre, todas las zonas)
  - catalogo.json  solo el municipio que estaba seleccionado en la muestra;
                   la región del resto solo se sabe con un postback
  - tarifas.json   el único mes que trae la muestra

No sobreescribe registros ya capturados.
"""
import json
import pathlib
from datetime import datetime, timezone

import parser as P

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DATA = RAIZ / "data"
MUESTRA = RAIZ / "scraper" / "muestra" / "GranDemandaMTH.html"
FUENTE = ("https://app.cfe.mx/Aplicaciones/CCFE/Tarifas/TarifasCRENegocio/"
          "Tarifas/GranDemandaMTH.aspx")

html = MUESTRA.read_text(encoding="utf-8", errors="replace")
ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
DATA.mkdir(parents=True, exist_ok=True)


def leer(nombre, vacio):
    ruta = DATA / nombre
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else vacio


def escribir(nombre, datos):
    (DATA / nombre).write_text(
        json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"  {nombre}")


print("Sembrando data/ desde la muestra:")

escribir("horarios.json", {"generado": ahora, "fuente": FUENTE,
                           "zonas": P.parsear_horarios(html)})

eid, estado = P.seleccionado(html, P.DD_ESTADO)
mid, municipio = P.seleccionado(html, P.DD_MUNICIPIO)
rid, region = P.seleccionado(html, P.DD_REGION)

cat = leer("catalogo.json", {"generado": None, "fuente": FUENTE,
                             "parcial": True, "estados": {}})
entrada = cat["estados"].setdefault(P.normalizar(estado),
                                    {"id": eid, "nombre": estado, "municipios": {}})
entrada["municipios"].setdefault(P.normalizar(municipio), {
    "id": mid, "nombre": municipio,
    "region": P.normalizar(region), "region_id": rid})
cat["generado"] = ahora
escribir("catalogo.json", cat)

r = P.parsear_cargos(html)
anio = int("20" + r["periodo_cfe"].split("-")[1])
mes = P.MESES.index([m for m in P.MESES if m.startswith(r["periodo_cfe"][:3])][0]) + 1

tar = leer("tarifas.json", {"actualizado": None, "fuente": FUENTE, "registros": {}})
clave = f"{r['tarifa']}|{P.normalizar(r['region'])}|{anio}-{mes:02d}"
tar["registros"].setdefault(clave, {
    "tarifa": r["tarifa"], "region": P.normalizar(r["region"]),
    "anio": anio, "mes": mes, "periodo_cfe": r["periodo_cfe"],
    "cargos": r["cargos"], "unidades": r["unidades"], "conceptos": r["conceptos"],
    "municipio_consultado": f"{municipio}, {estado}",
    "fuente": FUENTE, "fecha_captura": ahora,
})
tar["actualizado"] = ahora
escribir("tarifas.json", tar)

print(f"\nSembrado: {clave}")
print("El catálogo quedó PARCIAL (1 municipio). Corre construir_catalogo.py "
      "para completarlo.")
