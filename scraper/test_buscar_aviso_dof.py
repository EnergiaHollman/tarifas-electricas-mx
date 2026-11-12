# -*- coding: utf-8 -*-
"""Pruebas de la búsqueda del aviso en el índice del DOF, sin red. `python3 test_buscar_aviso_dof.py`."""
import contextlib
import datetime
import hashlib
import io
import pathlib
import sys

import requests

import buscar_aviso_dof as B

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MUESTRA = pathlib.Path(__file__).parent / "muestra"
fallos = []


def check(nombre, obtenido, esperado):
    if obtenido == esperado:
        print(f"  ok   {nombre}")
    else:
        print(f"  FALLA {nombre}\n        esperado: {esperado!r}\n        obtenido: {obtenido!r}")
        fallos.append(nombre)


INDICE = (MUESTRA / "DOF_indice_2026-09-30_recortado.html").read_text(encoding="latin-1")
VACIO = "<html><body><a href=\"/nota_detalle.php?codigo=1&fecha=x\">Otra nota cualquiera</a></body></html>"
D = datetime.date

print("Índice real del 30 de septiembre de 2026")
t = B.titulos_del_dia(INDICE)
check("dos notas, sin repetir códigos", [c for c, _ in t], ["5800037", "5800039"])
check("el aviso de tarifas trae su mes", [B.periodo_del_titulo(x) for _, x in t], [None, "2026-09"])
check("un título parecido sin «a partir del 1 de…» no cuenta",
      B.periodo_del_titulo("Tarifas Finales del Suministro Básico de otra cosa"), None)
check("el mes se lee con acentos y mayúsculas",
      B.periodo_del_titulo("TARIFAS FINALES DEL SUMINISTRO BÁSICO ... A PARTIR DEL 1 DE MARZO DE 2026"), "2026-03")

print("\nRango por omisión")
check("noviembre, hoy a mitad de mes: del 15 de octubre a hoy",
      B.rango_por_omision("2026-11", D(2026, 11, 12)), (D(2026, 10, 15), D(2026, 11, 12)))
check("noviembre, hoy ya pasó el 15 de diciembre: tope el 15 de diciembre",
      B.rango_por_omision("2026-11", D(2027, 3, 1)), (D(2026, 10, 15), D(2026, 12, 15)))
check("enero arranca el 15 de diciembre",
      B.rango_por_omision("2027-01", D(2027, 3, 1))[0], D(2026, 12, 15))

print("\nRecorrido")
leidos = []
def leer_falso(dia):
    leidos.append(dia)
    return INDICE if dia == D(2026, 9, 30) else VACIO
pausas = []
h, sin, rev = B.buscar("2026-09", D(2026, 9, 28), D(2026, 10, 3), leer=leer_falso, dormir=pausas.append)
check("lo encuentra el 30 y con su código", [(d, c) for d, c, _ in h], [(D(2026, 9, 30), "5800039")])
check("se detiene en el primero: no lee los días siguientes", leidos, [D(2026, 9, 28), D(2026, 9, 29), D(2026, 9, 30)])
check("2 s entre peticiones, no antes de la primera", pausas, [2.0, 2.0])
h, sin, rev = B.buscar("2026-11", D(2026, 11, 1), D(2026, 11, 5), leer=lambda d: VACIO, dormir=lambda s: None)
check("sin aviso: nada hallado y todos los días leídos", (h, sin, rev), ([], [], 5))
h, sin, rev = B.buscar("2026-10", D(2026, 9, 28), D(2026, 10, 1), leer=leer_falso, dormir=lambda s: None)
check("el aviso de septiembre no vale como el de octubre", h, [])

def leer_roto(dia):
    if dia == D(2026, 11, 3):
        raise requests.ConnectionError("sin red")
    return VACIO
h, sin, rev = B.buscar("2026-11", D(2026, 11, 1), D(2026, 11, 5), leer=leer_roto, dormir=lambda s: None)
check("un día ilegible se anota y se sigue", ([d for d, _ in sin], rev), ([D(2026, 11, 3)], 4))

print("\nmain(): mensajes, códigos de salida y que no escribe nada")
avisos = RAIZ / "data" / "avisos_dof.json"
antes = hashlib.sha256(avisos.read_bytes()).hexdigest()

def correr(argv, leer, hoy=D(2026, 11, 12)):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = B.main(argv, leer=leer, hoy=hoy, dormir=lambda s: None)
    return codigo, buf.getvalue()

codigo, salida = correr(["--mes", "2026-09", "--desde", "2026-09-29", "--hasta", "2026-10-01"], leer_falso, hoy=D(2026, 10, 5))
check("encontrado: sale 0", codigo, 0)
check("imprime el código y la línea para avisos_dof.json",
      '"2026-09": 5800039' in salida and "actualizar_dof.py --meses 2026-09" in salida, True)
check("dice que no escribió nada", "no escribió nada" in salida, True)
codigo, salida = correr(["--mes", "2026-11"], lambda d: VACIO)
check("no encontrado: sale 1 y lo dice", (codigo, "No encontrado" in salida and "Todavía no sale" in salida), (1, True))
codigo, salida = correr(["--mes", "2026-11"], leer_roto)
check("día ilegible y sin hallazgo: sale 2, no concluye y dice cuáles",
      (codigo, "No se pudo concluir" in salida and "2026-11-03" in salida), (2, True))
codigo, salida = correr(["--mes", "2026-12"], lambda d: VACIO, hoy=D(2026, 11, 12))
check("mes futuro sin días que revisar: sale 1 sin leer nada", (codigo, "Rango vacío" in salida), (1, True))
codigo, _ = correr(["--mes", "noviembre"], lambda d: VACIO)
check("mes mal escrito: sale 2", codigo, 2)
codigo, _ = correr(["--mes", "2026-11", "--desde", "ayer"], lambda d: VACIO)
check("fecha mal escrita: sale 2", codigo, 2)
check("avisos_dof.json no cambió", hashlib.sha256(avisos.read_bytes()).hexdigest(), antes)

print()
if fallos:
    print(f"{len(fallos)} prueba(s) fallaron.")
    sys.exit(1)
print("Todas las pruebas pasaron.")
