# -*- coding: utf-8 -*-
"""Pruebas del guardián contra sesiones con la región contaminada.

Esto pasó de verdad en un backfill real: una sesión reutilizada (cookie de
CFE) dejó seleccionada 'Valle de México Sur' aunque el código pidió 'Baja
California' con el mismo id que en otro momento correspondía a Baja
California, y el código viejo -que solo comparaba el id, nunca el nombre
visible- lo dio por bueno. El resultado: meses de 2023 a 2025 quedaron
guardados bajo 'BAJA CALIFORNIA' con los cargos reales de otra región.

Estas pruebas no tocan la red: fabrican HTML mínimo con solo el <select> de
división que hace falta para ejercitar `poner_region` y `_verificar_region`.
`python3 test_cfe_session.py`.
"""
import sys

import cfe
import parser as P

fallos = []


def check(nombre, obtenido, esperado):
    if obtenido == esperado:
        print(f"  ok   {nombre}")
    else:
        print(f"  FALLA {nombre}\n        esperado: {esperado!r}\n        obtenido: {obtenido!r}")
        fallos.append(nombre)


def select_html(seleccionado_id, seleccionado_texto, otras=()):
    opciones = [f'<option value="0">-- Selecciona --</option>']
    vistas = {seleccionado_id}
    opciones.append(f'<option value="{seleccionado_id}" selected="selected">{seleccionado_texto}</option>')
    for vid, texto in otras:
        if vid not in vistas:
            opciones.append(f'<option value="{vid}">{texto}</option>')
            vistas.add(vid)
    return (f'<select name="{P.DD_REGION}">' + "".join(opciones) + "</select>")


def sesion_falsa():
    """SesionCFE sin red: .abrir()/._postback() no hacen ninguna petición."""
    s = cfe.SesionCFE.__new__(cfe.SesionCFE)
    s.html = None
    s.pausa = 0
    return s


print("_verificar_region: la unidad mínima del guardián")
s = sesion_falsa()
try:
    s._verificar_region("Baja California", "BAJA CALIFORNIA", ya_seleccionada=True)
    check("nombre correcto: no revienta", True, True)
except cfe.ErrorCFE:
    check("nombre correcto: no revienta", False, True)

try:
    s._verificar_region("Valle de México Sur", "BAJA CALIFORNIA", ya_seleccionada=True)
    check("nombre distinto: sí revienta", False, True)
except cfe.ErrorCFE as e:
    check("nombre distinto: sí revienta", True, True)
    check("el mensaje nombra ambas regiones",
          "BAJA CALIFORNIA" in str(e) and "Valle de México Sur" in str(e), True)

check("sin etiqueta_esperada: no valida nada (compatibilidad)",
      s._verificar_region("cualquier cosa", None, ya_seleccionada=True) is None, True)

print("\nponer_region: reproduce el bug real")

# Caso 1: exactamente el escenario que ocurrió. El id "3" YA está
# seleccionado (por eso el código viejo no hacía nada), pero el texto visible
# es de otra división. poner_region no debe llamar a _postback -no hace
# falta, el id ya coincide- pero SÍ debe reventar en vez de seguir en
# silencio con el dato contaminado.
s = sesion_falsa()
s.html = select_html("3", "Valle de México Sur")
s._postback = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debería reintentar el postback"))
try:
    s.poner_region("3", etiqueta_esperada="BAJA CALIFORNIA")
    check("id ya seleccionado pero nombre equivocado: revienta", False, True)
except cfe.ErrorCFE as e:
    check("id ya seleccionado pero nombre equivocado: revienta", True, True)
    check("dice que 'ya estaba seleccionada'", "ya estaba seleccionada" in str(e), True)
except AssertionError as e:
    check("id ya seleccionado pero nombre equivocado: revienta", False, str(e))

# Caso 2: el id NO coincide, se hace el postback, pero el resultado sigue
# mostrando la región equivocada (la sesión del servidor "gana").
s = sesion_falsa()
s.html = select_html("9", "Otra región cualquiera")
def postback_que_no_cambia_nada(control, cambios):
    # El servidor "ignora" el cambio pedido: sigue devolviendo la misma
    # división contaminada, como pasaría con una sesión con memoria propia.
    s.html = select_html("9", "Valle de México Sur")
s._postback = postback_que_no_cambia_nada
try:
    s.poner_region("7", etiqueta_esperada="BAJA CALIFORNIA")
    check("postback no logra cambiar la región: revienta", False, True)
except cfe.ErrorCFE as e:
    check("postback no logra cambiar la región: revienta", True, True)
    check("dice que 'tras el postback'", "tras el postback" in str(e), True)

# Caso 3: el caso normal y sano. El postback sí deja la región correcta.
s = sesion_falsa()
s.html = select_html("9", "Otra región cualquiera")
def postback_correcto(control, cambios):
    s.html = select_html("7", "Baja California")
s._postback = postback_correcto
try:
    s.poner_region("7", etiqueta_esperada="BAJA CALIFORNIA")
    check("postback correcto: no revienta", True, True)
except cfe.ErrorCFE:
    check("postback correcto: no revienta", False, True)

# Caso 4: sin etiqueta_esperada (compatibilidad con las llamadas que no la
# pasan, como la resolución del catálogo). Debe comportarse como antes.
s = sesion_falsa()
s.html = select_html("3", "Cualquier cosa")
s._postback = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debería postear"))
try:
    s.poner_region("3")
    check("sin etiqueta_esperada: se comporta como antes (no valida)", True, True)
except Exception:
    check("sin etiqueta_esperada: se comporta como antes (no valida)", False, True)

print()
if fallos:
    print(f"{len(fallos)} prueba(s) fallaron: {', '.join(fallos)}")
    sys.exit(1)
print("Todas las pruebas pasaron.")
