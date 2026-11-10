# -*- coding: utf-8 -*-
"""Pruebas de seguridad del actualizador, sin red. `python3 test_actualizar_tarifas.py`.

Cubre lo que protege los datos ya capturados cuando se agregan tarifas:
  - --olvidar y --limpiar-todo solo tocan la tarifa pedida;
  - horarios.json no lo pisa una tarifa sin horarios;
  - una tabla incompleta (el defecto que tenía GDMTO/PDBT) no se guarda;
  - una respuesta sin tabla se reintenta antes de darse por "sin publicación";
  - los meses sospechosos salen en el resumen y como anotación de Actions.
"""
import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile

import actualizar_dac as D
import actualizar_tarifas as A
import cfe
import parser as P

MUESTRA = pathlib.Path(__file__).parent / "muestra"
HTML_GDMTH = (MUESTRA / "GranDemandaMTH.html").read_text(encoding="utf-8", errors="replace")
HTML_GDMTO = (MUESTRA / "GDMTO_2026-09_NOROESTE.html").read_text(encoding="utf-8", errors="replace")
HTML_PDBT = (MUESTRA / "PDBT_2026-03_NOROESTE.html").read_text(encoding="utf-8", errors="replace")
HTML_DAC = (MUESTRA / "DAC_2026-09.html").read_text(encoding="utf-8", errors="replace")
HTML_VACIO = "<html><body><p>sin resultados</p></body></html>"

fallos = []


def check(nombre, obtenido, esperado):
    if obtenido == esperado:
        print(f"  ok   {nombre}")
    else:
        print(f"  FALLA {nombre}\n        esperado: {esperado!r}\n        obtenido: {obtenido!r}")
        fallos.append(nombre)


def reg(tarifa, region, mes=1):
    return {f"{tarifa}|{region}|2026-{mes:02d}": {"tarifa": tarifa, "region": region,
                                                   "anio": 2026, "mes": mes}}


def dos_tarifas():
    r = {}
    for t in ("GDMTH", "GDMTO"):
        for region in ("NOROESTE", "NORTE"):
            r.update(reg(t, region))
    return r


print("Banderas acotadas a la tarifa")
r = dos_tarifas()
fuera = A.olvidar_registros(r, "GDMTO", ["noroeste"])
check("olvidar NOROESTE de GDMTO borra solo ese registro", fuera, ["GDMTO|NOROESTE|2026-01"])
check("el NOROESTE de GDMTH sigue", "GDMTH|NOROESTE|2026-01" in r, True)
check("quedan 3", len(r), 3)
r = dos_tarifas()
check("limpiar GDMTO devuelve 2", A.limpiar_tarifa(r, "GDMTO"), 2)
check("GDMTH intacta tras limpiar GDMTO",
      sorted(r), ["GDMTH|NOROESTE|2026-01", "GDMTH|NORTE|2026-01"])

print("\nGuardia: claves de cargo por tarifa")
def completa(tarifa, html):
    return [cfe.tabla_completa(tarifa, t) for t in P.parsear_todas(html)]
check("GDMTH con seis cargos", completa("GDMTH", HTML_GDMTH), [True])
check("GDMTO con cuatro cargos", completa("GDMTO", HTML_GDMTO), [True])
check("PDBT con dos cargos", completa("PDBT", HTML_PDBT), [True])
check("una tabla de GDMTO no vale como PDBT", completa("PDBT", HTML_GDMTO), [False])
check("el defecto viejo (solo 'fijo') se rechaza",
      cfe.tabla_completa("GDMTO", {"cargos": {"fijo": 197.77}}), False)
check("GDMTH sin punta (transición de temporada) se acepta",
      cfe.tabla_completa("GDMTH", {"cargos": {k: 1 for k in
                                              ("fijo", "base", "intermedia", "distribucion", "capacidad")}}), True)
check("GDMTH sin base se acepta",
      cfe.tabla_completa("GDMTH", {"cargos": {k: 1 for k in
                                              ("fijo", "intermedia", "punta", "distribucion", "capacidad")}}), True)
check("solo GDMTH tiene horarios",
      [t for t in cfe.TARIFAS if cfe.tiene_horarios(t)], ["GDMTH"])
check("PAGINAS conserva las URL de siempre",
      cfe.PAGINAS["GDMTH"].endswith("TarifasCRENegocio/Tarifas/GranDemandaMTH.aspx"), True)


class SesionFalsa:
    """Sin red. `respuestas` es la lista de HTML que devuelve cada consultar()."""
    url = "https://ejemplo/cfe.aspx"

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.html = HTML_VACIO
        self.consultas = 0
        self.aperturas = 0

    def abrir(self):
        self.aperturas += 1
        return self

    def poner_anio(self, anio):
        pass

    def consultar(self, anio, mes, eid, mid, region_id=None, region_etiqueta=None):
        self.consultas += 1
        self.html = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]

    def horarios(self):
        raise AssertionError("una tarifa sin horarios no debe pedir horarios")

    def anios(self):
        return [2026]

    def meses(self):
        return [1, 2, 3]

    def _actual(self, control):
        return ("2026", "2026")


print("\nReintento cuando la página responde sin tabla")
s = SesionFalsa([HTML_VACIO, HTML_GDMTO])
tablas, intentos = A.consultar_con_reintento(s, 2026, 9, "26", "1921", "18", "NOROESTE", 2, 0)
check("la tabla llega en el segundo intento", (len(tablas), intentos), (1, 2))
check("reabrió la página para reintentar", s.aperturas, 1)
s = SesionFalsa([HTML_VACIO])
tablas, intentos = A.consultar_con_reintento(s, 2026, 9, "26", "1921", "18", "NOROESTE", 2, 0)
check("siempre vacía: 3 intentos y sin tabla", (tablas, intentos), ([], 3))
s = SesionFalsa([HTML_GDMTO])
tablas, intentos = A.consultar_con_reintento(s, 2026, 9, "26", "1921", "18", "NOROESTE", 2, 0)
check("con tabla a la primera no reintenta", (len(tablas), intentos, s.aperturas), (1, 1, 0))
class SesionContaminada(SesionFalsa):
    def consultar(self, *a, **k):
        raise cfe.ErrorCFE("región equivocada")
try:
    A.consultar_con_reintento(SesionContaminada([HTML_VACIO]), 2026, 9, "26", "1921", "18", "NOROESTE", 2, 0)
    check("una región equivocada no se reintenta: se propaga", False, True)
except cfe.ErrorCFE:
    check("una región equivocada no se reintenta: se propaga", True, True)


print("\nResumen: los sospechosos no pasan desapercibidos")
with tempfile.TemporaryDirectory() as d:
    resumen = pathlib.Path(d) / "resumen.md"
    previo = {k: os.environ.get(k) for k in ("GITHUB_STEP_SUMMARY", "GITHUB_ACTIONS")}
    os.environ["GITHUB_STEP_SUMMARY"] = str(resumen)
    os.environ["GITHUB_ACTIONS"] = "true"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        A.emitir_resumen(["NORTE 2026-03: tabla incompleta"], ["NORESTE 2026-02 (3 intentos)"], "GDMTO")
    salida = buf.getvalue()
    for k, v in previo.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    texto = resumen.read_text(encoding="utf-8")
    check("el resumen del job lista el sospechoso", "NORTE 2026-03: tabla incompleta" in texto, True)
    check("el resumen del job lista el hueco", "NORESTE 2026-02" in texto, True)
    check("anotación ::warning:: por sospechosos", "::warning title=Tarifas GDMTO: 1 mes(es) sospechoso(s)" in salida, True)
    check("anotación ::warning:: por huecos", "::warning title=Tarifas GDMTO: 1 mes(es) sin tabla" in salida, True)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    A.emitir_resumen([], [], "GDMTO")
check("sin alertas no escribe nada", buf.getvalue(), "")


print("\nmain() de punta a punta con una sesión simulada")
CATALOGO = {"generado": None, "fuente": "x", "expansiones": {}, "estados": {"SONORA": {
    "id": "26", "nombre": "SONORA", "municipios": {"NAVOJOA": {
        "id": "1921", "nombre": "NAVOJOA",
        "opciones": [{"etiqueta": "NOROESTE", "id": "18"}]}}}}}
HORARIOS_CENTINELA = {"generado": "centinela", "fuente": "x", "zonas": {"intacto": True}}


def correr(tarifa, html, extra=()):
    """Corre main() con datos en un directorio temporal. Devuelve (código, tarifas, horarios)."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "catalogo.json").write_text(json.dumps(CATALOGO), encoding="utf-8")
        (d / "horarios.json").write_text(json.dumps(HORARIOS_CENTINELA), encoding="utf-8")
        (d / "tarifas.json").write_text(json.dumps({
            "actualizado": "antes", "fuente": cfe.PAGINAS["GDMTH"],
            "registros": reg("GDMTH", "NOROESTE", 3)}), encoding="utf-8")
        A.DATA, A.CATALOGO, A.TARIFAS, A.HORARIOS = d, d / "catalogo.json", d / "tarifas.json", d / "horarios.json"
        sesion = SesionFalsa([html])
        original = cfe.SesionCFE
        cfe.SesionCFE = lambda *a, **k: sesion
        argv = sys.argv
        sys.argv = ["actualizar_tarifas.py", "--tarifa", tarifa, "--desde", "2026", "--hasta", "2026",
                    "--pausa", "0", *extra]
        codigo = 0
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                A.main()
        except SystemExit as e:
            codigo = e.code
        finally:
            cfe.SesionCFE, sys.argv = original, argv
        return (codigo, json.loads((d / "tarifas.json").read_text(encoding="utf-8")),
                json.loads((d / "horarios.json").read_text(encoding="utf-8")))


codigo, tarifas, horarios = correr("GDMTO", HTML_GDMTO)
regs = tarifas["registros"]
check("termina bien", codigo, 0)
check("el registro de GDMTH sigue", "GDMTH|NOROESTE|2026-03" in regs, True)
check("se guardó GDMTO con los cuatro cargos",
      regs["GDMTO|NOROESTE|2026-01"]["cargos"],
      {"fijo": 197.77, "energia": 1.261, "distribucion": 90.85, "capacidad": 327.96})
check("horarios.json no se tocó", horarios, HORARIOS_CENTINELA)

# El defecto original: una tabla donde solo sobrevive 'fijo'.
html_incompleto = HTML_GDMTO.replace("Variable (Energía)", "Texto raro").replace("Capacidad", "Texto raro").replace(
    "Distribución", "Texto raro")
codigo, tarifas, horarios = correr("GDMTO", html_incompleto)
regs = tarifas["registros"]
check("tabla incompleta: no se guarda ningún registro de GDMTO",
      [k for k in regs if k.startswith("GDMTO")], [])
check("tabla incompleta: el proceso termina con error (no en silencio)", codigo, 1)
check("tabla incompleta: GDMTH sigue", "GDMTH|NOROESTE|2026-03" in regs, True)

codigo, tarifas, _ = correr("GDMTO", HTML_GDMTO, extra=("--limpiar-todo",))
check("--limpiar-todo con GDMTO no borra GDMTH", "GDMTH|NOROESTE|2026-03" in tarifas["registros"], True)

print("\nDAC: guardias de la captura")
tablas_ok = P.parsear_dac(HTML_DAC)
check("las seis regiones, completas y con el periodo pedido: confiable", D.revisar(2026, 9, tablas_ok), None)
check("periodo esperado", D.periodo_esperado(2026, 9), "SEP-26")
motivo = D.revisar(2026, 9, tablas_ok[:5])
check("falta una región: sospechoso", motivo is not None and "seis esperadas" in motivo, True)
motivo = D.revisar(2026, 3, tablas_ok)
check("la página muestra otro mes que el pedido: sospechoso",
      motivo is not None and "MAR-26" in motivo and "SEP-26" in motivo, True)
rota = [dict(t) for t in tablas_ok]
rota[3] = {**rota[3], "cargos": {"fijo": 145.85}}
motivo = D.revisar(2026, 9, rota)
check("una región con solo el fijo: sospechoso", motivo is not None and "incompleta" in motivo, True)
extra = tablas_ok + [{**tablas_ok[0], "region": "VALLE DE MEXICO"}]
check("una región nueva: sospechoso", D.revisar(2026, 9, extra) is not None, True)


class SesionDAC:
    """Sin red: poner_mes() deja en .html la respuesta que toque."""
    url = "https://ejemplo/TarifaDAC.aspx"

    def __init__(self, respuestas, meses=(8, 9, 10)):
        self.respuestas = list(respuestas)
        self._meses = list(meses)
        self.html = HTML_VACIO
        self.aperturas = 0
        self.pedidos = []

    def abrir(self):
        self.aperturas += 1
        return self

    def poner_anio(self, anio):
        pass

    def poner_mes(self, mes):
        self.pedidos.append(mes)
        self.html = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]

    def anios(self):
        return [2026]

    def meses(self):
        return self._meses

    def _actual(self, control):
        return ("2026", "2026")

    def horarios(self):
        raise AssertionError("DAC no tiene horarios")


def captura_dac(respuestas, meses=(9,), registros=None, **kw):
    registros = {} if registros is None else registros
    s = SesionDAC(respuestas, meses=meses)
    r = D.capturar(s, registros, [2026], kw.get("filtro"), kw.get("rehacer", False),
                   kw.get("faltantes", False), kw.get("reintentos", 2), 0, lambda: "ahora", lambda: None)
    return s, r, registros


print("\nDAC: captura con una sesión simulada")
s, r, regs_dac = captura_dac([HTML_DAC])
check("un mes guarda seis registros", (r["nuevos"], r["sospechosos"]), (6, 0))
check("claves por región y mes", sorted(regs_dac), [
    "DAC|BAJA CALIFORNIA SUR|2026-09", "DAC|BAJA CALIFORNIA|2026-09", "DAC|CENTRAL|2026-09",
    "DAC|NOROESTE|2026-09", "DAC|NORTE Y NORESTE|2026-09", "DAC|SUR Y PENINSULAR|2026-09"])
nor = regs_dac["DAC|NOROESTE|2026-09"]
check("el registro tiene la forma de los demás (sin municipio: DAC no tiene ubicación)",
      sorted(nor), ["anio", "cargos", "conceptos", "fecha_captura", "fuente", "mes",
                    "periodo_cfe", "region", "tarifa", "unidades"])
check("cargos de Noroeste", nor["cargos"], {"fijo": 145.85, "energia": 6.143})
s, r, _ = captura_dac([HTML_DAC], registros=regs_dac)
check("un mes ya capturado se omite sin consultar", (r["nuevos"], r["omitidos"], s.pedidos), (0, 1, []))
s, r, _ = captura_dac([HTML_VACIO, HTML_DAC])
check("sin tabla a la primera: llega al reintentar (una apertura del año y una del reintento)",
      (r["nuevos"], s.aperturas), (6, 2))
s, r, _ = captura_dac([HTML_VACIO], meses=(9, 10))
check("siempre vacío en el mes 9 (hay un mes posterior): hueco confirmado",
      (r["nuevos"], len(r["vacios_confirmados"])), (0, 1))
s, r, _ = captura_dac([HTML_VACIO], meses=(8, 9))
check("el último mes vacío no es noticia", (r["vacios"], r["vacios_confirmados"]), (2, ["DAC 2026-08 (3 intentos)"]))
s, r, regs_mal = captura_dac([HTML_DAC], meses=(3,))
check("la página muestra septiembre cuando se pidió marzo: no se guarda",
      (r["nuevos"], r["sospechosos"], regs_mal), (0, 1, {}))
s, r, _ = captura_dac([HTML_DAC], meses=(8, 9, 10), filtro={9})
check("--meses limita lo que se consulta", s.pedidos, [9])


print("\nmain() de DAC de punta a punta")
def correr_dac(html, extra=(), meses=(9,)):
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "horarios.json").write_text(json.dumps(HORARIOS_CENTINELA), encoding="utf-8")
        (d / "tarifas.json").write_text(json.dumps({
            "actualizado": "antes", "fuente": cfe.PAGINAS["GDMTH"],
            "registros": reg("GDMTH", "NOROESTE", 3)}), encoding="utf-8")
        A.DATA, A.CATALOGO, A.TARIFAS, A.HORARIOS = d, d / "catalogo.json", d / "tarifas.json", d / "horarios.json"
        sesion = SesionDAC([html], meses=meses)
        original = cfe.SesionCFE
        cfe.SesionCFE = lambda *a, **k: sesion
        argv = sys.argv
        sys.argv = ["actualizar_tarifas.py", "--tarifa", "DAC", "--desde", "2026", "--hasta", "2026",
                    "--pausa", "0", *extra]
        codigo = 0
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                A.main()
        except SystemExit as e:
            codigo = e.code
        finally:
            cfe.SesionCFE, sys.argv = original, argv
        return (codigo, json.loads((d / "tarifas.json").read_text(encoding="utf-8")),
                json.loads((d / "horarios.json").read_text(encoding="utf-8")))


codigo, tarifas, horarios = correr_dac(HTML_DAC)
regs = tarifas["registros"]
check("termina bien sin catálogo (DAC no lo usa)", codigo, 0)
check("seis registros de DAC y el de GDMTH", sorted(k.split("|")[0] for k in regs),
      ["DAC"] * 6 + ["GDMTH"])
check("horarios.json no se tocó", horarios, HORARIOS_CENTINELA)
codigo, tarifas, _ = correr_dac(HTML_DAC, extra=("--meses", "3"), meses=(3,))
check("pedir marzo y recibir septiembre: sin registros de DAC y termina con error",
      ([k for k in tarifas["registros"] if k.startswith("DAC")], codigo), ([], 1))
codigo, tarifas, _ = correr_dac(HTML_DAC, extra=("--limpiar-todo",))
check("--limpiar-todo con DAC no borra GDMTH", "GDMTH|NOROESTE|2026-03" in tarifas["registros"], True)

print()
if fallos:
    print(f"{len(fallos)} prueba(s) fallaron: {', '.join(fallos)}")
    sys.exit(1)
print("Todas las pruebas pasaron.")
