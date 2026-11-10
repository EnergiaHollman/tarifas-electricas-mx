# -*- coding: utf-8 -*-
"""Pruebas de la captura de las domésticas, sin red. `python3 test_actualizar_domestica.py`.

Usa las muestras reales: para la 1F, septiembre de 2026 con inicio de verano en
febrero (fuera de verano) y en mayo (verano), que son exactamente los dos
inicios que captura el scraper; y la tarifa 1, que no tiene temporadas.
"""
import contextlib
import copy
import io
import json
import pathlib
import sys
import tempfile

import actualizar_domestica as D
import actualizar_tarifas as A
import cfe
import parser as P

MUESTRA = pathlib.Path(__file__).parent / "muestra"
leer = lambda n: (MUESTRA / f"{n}.html").read_text(encoding="utf-8", errors="replace")
HTML_1F_FUERA, HTML_1F_VERANO = leer("Dom1F_2026-09_ini2"), leer("Dom1F_2026-09_ini5")
HTML_1 = leer("Dom1_2026-09")
HTML_VACIO = "<html><body>sin resultados</body></html>"
fallos = []


def check(nombre, obtenido, esperado):
    if obtenido == esperado:
        print(f"  ok   {nombre}")
    else:
        print(f"  FALLA {nombre}\n        esperado: {esperado!r}\n        obtenido: {obtenido!r}")
        fallos.append(nombre)


print("Regla del verano: seis meses seguidos desde el de inicio")
# Casos comprobados contra la página de CFE (1A, abril, agosto y septiembre).
comprobados = [(4, 2, "verano"), (4, 3, "verano"), (4, 4, "verano"), (4, 5, "fuera_verano"),
               (8, 2, "fuera_verano"), (8, 3, "verano"), (8, 4, "verano"), (8, 5, "verano"),
               (9, 2, "fuera_verano"), (9, 3, "fuera_verano"), (9, 4, "verano"), (9, 5, "verano")]
check("los 12 casos que la página de CFE confirmó",
      [D.temporada_esperada(m, i) for m, i, _ in comprobados], [t for *_, t in comprobados])
check("enero, noviembre y diciembre son siempre fuera de verano con inicio en febrero o mayo",
      {D.temporada_esperada(m, i) for m in (1, 11, 12) for i in cfe.INICIOS_VERANO}, {"fuera_verano"})
check("mayo, junio y julio son siempre verano con inicio en febrero o mayo",
      {D.temporada_esperada(m, i) for m in (5, 6, 7) for i in cfe.INICIOS_VERANO}, {"verano"})
check("febrero y mayo bastan: todo mes tiene sus temporadas posibles cubiertas",
      all({D.temporada_esperada(m, i) for i in (2, 3, 4, 5)} == {D.temporada_esperada(m, i) for i in cfe.INICIOS_VERANO}
          for m in range(1, 13)), True)

print("\nEscalones")
ok = P.parsear_domestica(HTML_1F_VERANO)["escalones"]
check("límites contiguos y excedente sin tope: sin objeción", D.revisar_escalones(ok), None)
roto = copy.deepcopy(ok); roto[1]["desde_kwh"] = 310
check("un hueco entre escalones se detecta", "empieza en 310" in D.revisar_escalones(roto), True)
roto = copy.deepcopy(ok); roto[-1]["hasta_kwh"] = 9999
check("un excedente con tope se detecta", "excedente" in D.revisar_escalones(roto), True)
roto = copy.deepcopy(ok); roto[0]["hasta_kwh"] = 0
check("un escalón de tamaño cero se detecta", D.revisar_escalones(roto) is not None, True)

print("\nArmar el registro de un mes")
def tablas_1f(**cambios):
    return {2: P.parsear_domestica(HTML_1F_FUERA), 5: P.parsear_domestica(HTML_1F_VERANO), **cambios}
reg, motivo = D.armar("1F", 2026, 9, tablas_1f(), lambda: "ahora", "https://ejemplo")
check("septiembre de 1F: sin objeción", motivo, None)
check("un registro por mes, bajo NACIONAL, con ambas temporadas",
      (reg["region"], sorted(reg["temporadas"]), reg["minimo_mensual_kwh"], "cargos" in reg),
      ("NACIONAL", ["fuera_verano", "verano"], 25, False))
check("verano de 1F con cuatro escalones", list(reg["temporadas"]["verano"]["cargos"]),
      ["basico", "intermedio_bajo", "intermedio_alto", "excedente"])
check("fuera de verano de 1F con tres", list(reg["temporadas"]["fuera_verano"]["cargos"]),
      ["basico", "intermedio", "excedente"])
check("el registro trae lo que trae el resto", sorted(reg),
      ["anio", "fecha_captura", "fuente", "mes", "minimo_mensual_kwh", "periodo_cfe", "region", "tarifa", "temporadas"])

def motivo_de(tablas, mes=9, tarifa="1F"):
    return D.armar(tarifa, 2026, mes, tablas, lambda: "ahora", "x")[1]
check("la página muestra otro mes que el pedido", "se pidió MAR-26 pero la página muestra SEP-26" in (motivo_de(tablas_1f(), mes=3) or ""), True)
check("la página tiene otro inicio de verano que el pedido",
      "inicio de verano 5" in (motivo_de({5: P.parsear_domestica(HTML_1F_FUERA)}) or ""), True)
check("la temporada de la página contradice la regla del verano (inicio 2, mes 9: fuera de verano)",
      "la regla del verano da fuera_verano pero la página muestra verano" in (motivo_de({2: P.parsear_domestica(HTML_1F_VERANO) | {"inicio_verano": "2"}}) or ""), True)
tres = P.parsear_domestica(HTML_1F_FUERA) | {"temporada": "verano", "inicio_verano": "5"}
check("una tabla de verano de 1F con tres escalones: cargos distintos", "cargos distintos" in (motivo_de({5: tres}) or ""), True)
dist = copy.deepcopy(P.parsear_domestica(HTML_1F_VERANO)); dist["inicio_verano"] = "2"
dist2 = copy.deepcopy(dist); dist2["cargos"]["basico"] = 9.9; dist2["escalones"][0]["valor"] = 9.9
mismo = motivo_de({2: dist | {"temporada": "fuera_verano"}, 5: dist2 | {"temporada": "fuera_verano", "inicio_verano": "5"}}, mes=1)
check("dos inicios con la misma temporada y tablas distintas", mismo is not None, True)
sin_min = P.parsear_domestica(HTML_1F_FUERA) | {"minimo_mensual_kwh": None}
check("sin mínimo mensual", "mínimo mensual" in (motivo_de({2: sin_min, 5: P.parsear_domestica(HTML_1F_VERANO)}) or ""), True)
reg1, motivo = D.armar("1", 2026, 9, {None: P.parsear_domestica(HTML_1)}, lambda: "ahora", "x")
check("tarifa 1: cargos y escalones directos, sin temporadas", (motivo, "temporadas" in reg1, list(reg1["cargos"])),
      (None, False, ["basico", "intermedio", "excedente"]))
check("tarifa 1: una tabla con temporada es sospechosa",
      "no tiene temporadas" in (motivo_de({None: P.parsear_domestica(HTML_1F_VERANO)}, tarifa="1") or ""), True)


class SesionDomestica:
    """Sin red. responder(inicio, mes) -> HTML de lo que mostraría la página."""
    url = "https://ejemplo/Tarifa1F.aspx"

    def __init__(self, responder, meses=(9,)):
        self.responder, self._meses = responder, list(meses)
        self.html, self.inicio, self.aperturas, self.pedidos = HTML_VACIO, None, 0, []

    def abrir(self):
        self.aperturas += 1
        self.inicio = None
        return self

    def poner_anio(self, anio):
        pass

    def poner_inicio_verano(self, inicio):
        self.inicio = inicio

    def forzar_mes(self, mes):
        self.pedidos.append((self.inicio, mes))
        self.html = self.responder(self.inicio, mes)

    def anios(self):
        return [2026]

    def meses(self):
        return self._meses

    def _actual(self, control):
        return ("2026", "2026")

    def horarios(self):
        raise AssertionError("las domésticas no tienen horarios")


por_inicio = lambda i, m: {2: HTML_1F_FUERA, 5: HTML_1F_VERANO}[i]


def capturar(tarifa, responder, meses=(9,), registros=None, **kw):
    registros = {} if registros is None else registros
    s = SesionDomestica(responder, meses)
    r = D.capturar(s, registros, [2026], kw.get("filtro"), kw.get("rehacer", False), kw.get("faltantes", False),
                   kw.get("reintentos", 2), 0, lambda: "ahora", lambda: None, tarifa)
    return s, r, registros


print("\nCaptura con una sesión simulada")
s, r, regs = capturar("1F", por_inicio)
check("1F septiembre: un registro, sin sospechosos", (r["nuevos"], r["sospechosos"]), (1, 0))
check("la clave", sorted(regs), ["1F|NACIONAL|2026-09"])
check("pidió febrero y mayo, en una pasada cada uno", s.pedidos, [(2, 9), (5, 9)])
s2, r2, _ = capturar("1F", por_inicio, registros=regs)
check("un mes ya capturado se omite sin consultar", (r2["nuevos"], r2["omitidos"], s2.pedidos), (0, 1, []))
s, r, regs1 = capturar("1", lambda i, m: HTML_1)
check("tarifa 1: una sola consulta, sin inicio de verano", (r["nuevos"], s.pedidos), (1, [(None, 9)]))
check("tarifa 1: la clave", sorted(regs1), ["1|NACIONAL|2026-09"])
llamadas = []
def vacia_la_primera(i, m):
    llamadas.append((i, m)); return HTML_VACIO if len(llamadas) == 1 else por_inicio(i, m)
s, r, _ = capturar("1F", vacia_la_primera)
check("sin tabla a la primera: llega al reintentar (una apertura del año y una del reintento)", (r["nuevos"], s.aperturas), (1, 2))
s, r, _ = capturar("1F", lambda i, m: HTML_VACIO, meses=(9, 10))
check("siempre vacío con meses posteriores: hueco confirmado", (r["nuevos"], r["vacios"], r["vacios_confirmados"]),
      (0, 2, ["1F 2026-09"]))
s, r, rg = capturar("1F", lambda i, m: HTML_1F_VERANO)
check("la página devuelve siempre verano aunque se pida febrero: no se guarda",
      (r["nuevos"], r["sospechosos"], rg), (0, 1, {}))
s, r, rg = capturar("1F", por_inicio, meses=(3,))
check("se pide marzo y la página muestra septiembre: no se guarda", (r["nuevos"], r["sospechosos"], rg), (0, 1, {}))
roto = HTML_1F_VERANO.replace("los primeros 300", "los primerísimos 300")
check("la mutación de la prueba sí cambió el HTML", roto != HTML_1F_VERANO, True)
s, r, rg = capturar("1F", lambda i, m: HTML_1F_FUERA if i == 2 else roto)
check("un texto no reconocido de CFE: sospechoso, no revienta la corrida",
      (r["nuevos"], r["sospechosos"], "no se reconoce el tamaño del escalón" in " ".join(r["alertas"])), (0, 1, True))
s, r, _ = capturar("1F", por_inicio, meses=(8, 9, 10), filtro={9})
check("--meses limita lo que se consulta", s.pedidos, [(2, 9), (5, 9)])
def un_inicio_sin_tabla(i, m):
    return HTML_1F_FUERA if i == 2 else HTML_VACIO
s, r, rg = capturar("1F", un_inicio_sin_tabla, reintentos=0)
check("solo uno de los dos inicios responde: sospechoso, no un mes a medias",
      (r["nuevos"], r["sospechosos"], rg), (0, 1, {}))


print("\nmain() de punta a punta")
HORARIOS = {"generado": "centinela", "fuente": "x", "zonas": {"intacto": True}}
def correr(tarifa, responder, meses=(9,), extra=()):
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "horarios.json").write_text(json.dumps(HORARIOS), encoding="utf-8")
        (d / "tarifas.json").write_text(json.dumps({"actualizado": "antes", "fuente": cfe.PAGINAS["GDMTH"],
            "registros": {"GDMTH|NOROESTE|2026-03": {"tarifa": "GDMTH", "region": "NOROESTE", "anio": 2026, "mes": 3}}}),
            encoding="utf-8")
        A.DATA, A.CATALOGO, A.TARIFAS, A.HORARIOS = d, d / "catalogo.json", d / "tarifas.json", d / "horarios.json"
        sesion = SesionDomestica(responder, meses)
        original, argv = cfe.SesionCFE, sys.argv
        cfe.SesionCFE = lambda *a, **k: sesion
        sys.argv = ["actualizar_tarifas.py", "--tarifa", tarifa, "--desde", "2026", "--hasta", "2026", "--pausa", "0", *extra]
        codigo = 0
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                A.main()
        except SystemExit as e:
            codigo = e.code
        finally:
            cfe.SesionCFE, sys.argv = original, argv
        return codigo, json.loads((d / "tarifas.json").read_text(encoding="utf-8")), json.loads((d / "horarios.json").read_text(encoding="utf-8"))


codigo, tarifas, horarios = correr("1F", por_inicio)
check("termina bien y sin catálogo", codigo, 0)
check("el registro de 1F y el de GDMTH", sorted(tarifas["registros"]), ["1F|NACIONAL|2026-09", "GDMTH|NOROESTE|2026-03"])
check("horarios.json no se tocó", horarios, HORARIOS)
codigo, tarifas, _ = correr("1F", lambda i, m: HTML_1F_VERANO)
check("una captura sospechosa termina con error y no guarda nada de 1F",
      (codigo, [k for k in tarifas["registros"] if k.startswith("1F")]), (1, []))
codigo, tarifas, _ = correr("1F", por_inicio, extra=("--limpiar-todo",))
check("--limpiar-todo de 1F no borra GDMTH", "GDMTH|NOROESTE|2026-03" in tarifas["registros"], True)
codigo, tarifas, _ = correr("1", lambda i, m: HTML_1)
check("la tarifa 1 también", (codigo, sorted(tarifas["registros"])), (0, ["1|NACIONAL|2026-09", "GDMTH|NOROESTE|2026-03"]))

print()
if fallos:
    print(f"{len(fallos)} prueba(s) fallaron: {', '.join(fallos)}")
    sys.exit(1)
print("Todas las pruebas pasaron.")
