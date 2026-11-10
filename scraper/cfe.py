# -*- coding: utf-8 -*-
"""Cliente del portal de tarifas de CFE (ASP.NET WebForms).

El portal no tiene API: cada desplegable dispara un postback completo contra
la misma .aspx, reenviando __VIEWSTATE y __EVENTVALIDATION. Esta clase
mantiene la sesión y encadena los postbacks en el orden correcto.

La sesión recuerda qué hay seleccionado y solo repite los postbacks que hacen
falta. Para el backfill eso importa: recorrer 12 meses de una misma región
cuesta 12 postbacks en lugar de 60.

Uso previsto: una corrida mensual. No está pensado para consultas en vivo;
para eso está la API, que lee del JSON ya capturado.
"""
import os
import time

import requests

import parser as P

_NEGOCIO = "https://app.cfe.mx/Aplicaciones/CCFE/Tarifas/TarifasCRENegocio/Tarifas/"

# Qué sabe el scraper de cada tarifa. `cargos_validos` son los conjuntos de
# claves que una tabla completa puede traer; cualquier otra combinación es una
# captura incompleta y NO se guarda (ver tabla_completa). Es lo que impide que
# un parser que pierde filas deje registros que parecen buenos.
#
# GDMTH admite tres: los seis cargos, y los meses de transición de temporada en
# que CFE no publica uno de los dos extremos (sin punta, o sin base).
TARIFAS = {
    "GDMTH": {
        "url": _NEGOCIO + "GranDemandaMTH.aspx",
        "tiene_horarios": True,
        "estructura": "negocio",
        "cargos_validos": [
            frozenset({"fijo", "base", "intermedia", "punta", "distribucion", "capacidad"}),
            frozenset({"fijo", "base", "intermedia", "distribucion", "capacidad"}),
            frozenset({"fijo", "intermedia", "punta", "distribucion", "capacidad"}),
        ],
    },
    # El resto del portal de negocio usa exactamente la misma mecánica.
    "GDMTO": {
        "url": _NEGOCIO + "GranDemandaMTO.aspx",
        "tiene_horarios": False,
        "estructura": "negocio",
        "cargos_validos": [frozenset({"fijo", "energia", "distribucion", "capacidad"})],
    },
    "PDBT": {
        "url": _NEGOCIO + "PequenaDemandaBT.aspx",
        "tiene_horarios": False,
        "estructura": "negocio",
        "cargos_validos": [frozenset({"fijo", "energia"})],
    },
    # DAC vive en otra carpeta del portal (TarifasCRECasa) y no tiene estado,
    # municipio ni división: solo año y mes. La página trae las seis regiones
    # de DAC juntas. Baja California y Baja California Sur tienen energía de
    # verano y de fuera de verano; las demás, un solo precio.
    "DAC": {
        "url": "https://app.cfe.mx/Aplicaciones/CCFE/Tarifas/TarifasCRECasa/Tarifas/TarifaDAC.aspx",
        "tiene_horarios": False,
        "estructura": "dac",
        "cargos_validos": [
            frozenset({"fijo", "energia"}),
            frozenset({"fijo", "energia_verano", "energia_fuera_verano"}),
        ],
    },
}

# Domésticas. Viven en TarifasCRECasa, no piden estado, municipio ni división (el
# precio es nacional) y, de la 1A a la 1F, dependen de la temporada de verano de
# la localidad: la página pide "el mes en que comienza el verano" (febrero a
# mayo) y el verano dura seis meses seguidos desde ese mes. La 1 no tiene
# temporadas. Las 1C a 1F traen cuatro escalones en verano (dos "intermedio",
# bajo y alto) y tres fuera de verano; la 1, la 1A y la 1B, tres siempre.
_CASA = "https://app.cfe.mx/Aplicaciones/CCFE/Tarifas/TarifasCRECasa/Tarifas/"
_TRES = frozenset({"basico", "intermedio", "excedente"})
_CUATRO = frozenset({"basico", "intermedio_bajo", "intermedio_alto", "excedente"})
REGION_NACIONAL = "NACIONAL"
# Mes en que comienza el verano que ofrece la página; con febrero y mayo se
# obtienen las dos temporadas de cualquier mes (comprobado contra marzo y abril).
INICIOS_VERANO = (2, 5)
TEMP_DOMESTICAS = {
    "1": ("sin temporadas", {None: [_TRES]}),
    "1A": ("temperatura media mínima en verano de 25 °C", {"verano": [_TRES], "fuera_verano": [_TRES]}),
    "1B": ("temperatura media mínima en verano de 28 °C", {"verano": [_TRES], "fuera_verano": [_TRES]}),
    "1C": ("temperatura media mínima en verano de 30 °C", {"verano": [_CUATRO], "fuera_verano": [_TRES]}),
    "1D": ("temperatura media mínima en verano de 31 °C", {"verano": [_CUATRO], "fuera_verano": [_TRES]}),
    "1E": ("temperatura media mínima en verano de 32 °C", {"verano": [_CUATRO], "fuera_verano": [_TRES]}),
    "1F": ("temperatura media mínima en verano de 33 °C", {"verano": [_CUATRO], "fuera_verano": [_TRES]}),
}
for _clave_dom, (_desc, _validos) in TEMP_DOMESTICAS.items():
    TARIFAS[_clave_dom] = {
        "url": _CASA + f"Tarifa{_clave_dom}.aspx",
        "tiene_horarios": False,
        "estructura": "domestica",
        "temporadas": _clave_dom != "1",
        "cargos_validos": _validos,
    }

# Las regiones que publica la tabla de DAC. No son las 17 divisiones de GDMTH.
# Si CFE agrega, quita o renombra una, la captura de ese mes es sospechosa en
# vez de guardarse a medias.
REGIONES_DAC = frozenset({"BAJA CALIFORNIA", "BAJA CALIFORNIA SUR", "CENTRAL",
                          "NOROESTE", "NORTE Y NORESTE", "SUR Y PENINSULAR"})


def estructura(tarifa):
    """'negocio' (estado, municipio, división), 'dac' (año y mes) o 'domestica'."""
    return TARIFAS[tarifa]["estructura"]

# Compatibilidad: el resto del código sigue pidiendo la URL por aquí.
PAGINAS = {clave: meta["url"] for clave, meta in TARIFAS.items()}


def tabla_completa(tarifa, tabla):
    """¿La tabla trae exactamente las claves de cargo que esa tarifa publica?

    En las domésticas la lista de claves válidas depende de la temporada de la
    tabla (cuatro escalones en verano en la 1C a la 1F, tres fuera de verano).
    """
    validos = TARIFAS[tarifa]["cargos_validos"]
    if isinstance(validos, dict):
        validos = validos.get(tabla.get("temporada"), [])
    return frozenset(tabla["cargos"]) in validos


def tiene_horarios(tarifa):
    return TARIFAS[tarifa]["tiene_horarios"]


# Un User-Agent de navegador sin la huella TLS real de un navegador es peor
# que uno honesto: un firewall puede bloquear por completo la combinación
# "dice ser Chrome pero no negocia TLS como Chrome" (se probó y dio 403
# desde la primera petición). Mejor ser honesto sobre qué es este acceso.
AGENTE = ("tarifas-electricas-mx/1.0 (consulta mensual automatizada de tarifas "
          "publicas; https://github.com/EnergiaHollman/tarifas-electricas-mx)")
CABECERAS_COMUNES = {"Accept-Language": "es-MX,es;q=0.9"}


class ErrorCFE(RuntimeError):
    pass


class SesionCFE:
    """Una sesión contra una página de tarifas."""

    def __init__(self, tarifa="GDMTH", pausa=1.5, timeout=45, reintentos=3,
                 verificar_tls=None, cookies=None):
        if tarifa not in PAGINAS:
            raise ErrorCFE(f"tarifa desconocida: {tarifa}")
        self.tarifa = tarifa
        self.url = PAGINAS[tarifa]
        self.pausa = pausa
        self.timeout = timeout
        self.reintentos = reintentos
        self.html = None
        # El servidor de CFE no manda la cadena completa de certificados, y en
        # Linux eso rompe la verificación. preparar_tls.py arma un bundle que
        # sí la trae; requests lo toma solo de REQUESTS_CA_BUNDLE.
        if verificar_tls is None:
            verificar_tls = os.environ.get("CFE_TLS_INSEGURO", "") not in ("1", "true", "si")
        self.verificar = verificar_tls
        if not self.verificar:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            print("AVISO: verificación TLS desactivada.")
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": AGENTE, **CABECERAS_COMUNES})

        # Soporte de cookies dejado por compatibilidad, pero NO hace falta en
        # uso normal. Se agregó cuando se sospechaba que un firewall
        # (Imperva Incapsula) degradaba la respuesta a sesiones sin aprobar
        # por un navegador real. Esa hipótesis resultó ser falsa: la causa
        # real de que el histórico no se pudiera traer era que el control de
        # mes cambia de nombre según el año (ver control_mes en parser.py),
        # nada que tuviera que ver con cookies. Confirmado sin cookies: el
        # scraper trae histórico igual. Se deja el parámetro por si algún
        # día aparece un problema genuino de sesión, pero no se necesita
        # configurar CFE_COOKIES para nada del funcionamiento normal.
        cookies = cookies if cookies is not None else os.environ.get("CFE_COOKIES", "")
        if cookies:
            n = 0
            for par in cookies.split(";"):
                if "=" in par:
                    k, v = par.strip().split("=", 1)
                    self.s.cookies.set(k, v, domain="app.cfe.mx")
                    n += 1
            print(f"[cfe] usando {n} cookie(s) de una sesión real")

    # -- transporte --------------------------------------------------------

    def _pedir(self, metodo, **kw):
        ultimo = None
        for intento in range(self.reintentos):
            try:
                r = self.s.request(metodo, self.url, timeout=self.timeout,
                                   verify=self.verificar, **kw)
                r.raise_for_status()
                if "__VIEWSTATE" not in r.text:
                    raise ErrorCFE("la respuesta no parece la página de tarifas")
                self.html = r.text
                time.sleep(self.pausa)
                return r.text
            except Exception as e:           # noqa: BLE001
                ultimo = e
                time.sleep(self.pausa * (intento + 2))
        raise ErrorCFE(f"no se pudo contactar a CFE: {ultimo}")

    def abrir(self):
        self._pedir("GET")
        return self

    def _postback(self, objetivo, cambios):
        if self.html is None:
            self.abrir()
        datos = P.campos_formulario(self.html)
        datos.update(cambios)
        datos["__EVENTTARGET"] = objetivo
        datos["__EVENTARGUMENT"] = ""
        datos["__LASTFOCUS"] = ""
        return self._pedir("POST", data=datos,
                           headers={"Referer": self.url,
                                    "Content-Type": "application/x-www-form-urlencoded"})

    # -- selección ---------------------------------------------------------

    def _actual(self, control):
        # DD_MES es un alias especial: resuelve al control de mes que exista
        # de verdad en la página en este momento (cambia según el año).
        if control == P.DD_MES:
            control = P.control_mes(self.html) or control
        return P.seleccionado(self.html, control)

    def anios(self):
        if self.html is None:
            self.abrir()
        return [int(v) for v, _, _ in P.opciones(self.html, P.DD_ANIO)]

    def meses(self):
        """Meses publicados para el año seleccionado.

        En el año en curso CFE solo lista los meses ya publicados, así que hay
        que leerlos en vez de asumir 12. Para años pasados, el control de mes
        es otro por completo (ver control_mes en parser.py).
        """
        control = P.control_mes(self.html)
        if control is None:
            return []
        return [int(v) for v, _, _ in P.opciones(self.html, control)]

    def estados(self):
        if self.html is None:
            self.abrir()
        return [(v, t) for v, t, _ in P.opciones(self.html, P.DD_ESTADO)]

    def municipios(self):
        return [(v, t) for v, t, _ in P.opciones(self.html, P.DD_MUNICIPIO)]

    def regiones_disponibles(self):
        return [(v, t) for v, t, _ in P.opciones(self.html, P.DD_REGION)]

    def poner_anio(self, anio):
        actual, _ = self._actual(P.DD_ANIO)
        if actual == str(anio):
            return
        self._postback(P.DD_ANIO, {P.DD_ANIO: str(anio)})

    def poner_mes(self, mes):
        control = P.control_mes(self.html)
        if control is None:
            raise ErrorCFE("la página no tiene ningún control de mes ahora mismo "
                           "(revisa meses() antes de llamar a poner_mes)")
        actual, _ = self._actual(control)
        if actual == str(mes):
            return
        # Enviar un mes que ya no está entre las opciones hace que el
        # servidor responda 500 (el __EVENTVALIDATION lo rechaza). Puede
        # pasar si el año cambió y el mes pedido ya no aplica.
        ofrecidos = [v for v, _, _ in P.opciones(self.html, control)]
        if str(mes) not in ofrecidos:
            raise ErrorCFE(f"mes {mes} no está entre los que ofrece la página "
                           f"ahora mismo ({ofrecidos}); hay que revisar meses() "
                           f"después del año antes de pedir un mes")
        self._postback(control, {control: str(mes)})

    def poner_inicio_verano(self, mes):
        """Domésticas 1A a 1F: mes en que comienza el verano (febrero a mayo)."""
        actual, _ = self._actual(P.DD_INICIO_VERANO)
        if actual == str(mes):
            return
        ofrecidos = [v for v, _, _ in P.opciones(self.html, P.DD_INICIO_VERANO)]
        if str(mes) not in ofrecidos:
            raise ErrorCFE(f"el inicio de verano {mes} no está entre los que ofrece la página ({ofrecidos})")
        self._postback(P.DD_INICIO_VERANO, {P.DD_INICIO_VERANO: str(mes)})

    def forzar_mes(self, mes):
        """Vuelve a pedir el mes aunque ya esté seleccionado.

        Cambiar el inicio de verano deja el mes puesto; pedirlo otra vez asegura
        que la tabla sea la del inicio nuevo y no la que quedó de antes.
        """
        control = P.control_mes(self.html)
        if control is None:
            raise ErrorCFE("la página no tiene ningún control de mes ahora mismo")
        ofrecidos = [v for v, _, _ in P.opciones(self.html, control)]
        if str(mes) not in ofrecidos:
            raise ErrorCFE(f"mes {mes} no está entre los que ofrece la página ({ofrecidos})")
        self._postback(control, {control: str(mes)})

    def poner_estado(self, estado_id):
        actual, _ = self._actual(P.DD_ESTADO)
        if actual == str(estado_id):
            return
        # Al cambiar de estado, municipio y región se repueblan: hay que
        # mandarlos en blanco o el servidor rechaza el postback por validación.
        self._postback(P.DD_ESTADO, {P.DD_ESTADO: str(estado_id),
                                     P.DD_MUNICIPIO: "0", P.DD_REGION: "0"})

    def poner_municipio(self, municipio_id):
        actual, _ = self._actual(P.DD_MUNICIPIO)
        if actual == str(municipio_id):
            return
        self._postback(P.DD_MUNICIPIO, {P.DD_MUNICIPIO: str(municipio_id),
                                        P.DD_REGION: "0"})

    def poner_region(self, region_id, etiqueta_esperada=None):
        actual, nombre = self._actual(P.DD_REGION)
        if actual == str(region_id):
            self._verificar_region(nombre, etiqueta_esperada, ya_seleccionada=True)
            return
        self._postback(P.DD_REGION, {P.DD_REGION: str(region_id)})
        _, nombre = self._actual(P.DD_REGION)
        self._verificar_region(nombre, etiqueta_esperada, ya_seleccionada=False)

    def _verificar_region(self, nombre_visible, etiqueta_esperada, ya_seleccionada):
        """El id no basta: si el sitio (o la cookie de sesión reutilizada)
        ya trae ese id apuntando a una división distinta, hay que notarlo en
        vez de guardar en silencio el dato de la región equivocada. Pasó de
        verdad: un backfill largo terminó guardando meses de 2023-2025 bajo
        'BAJA CALIFORNIA' con los cargos reales de 'VALLE DE MEXICO SUR'.
        """
        if etiqueta_esperada is None:
            return
        if P.normalizar(nombre_visible or "") != P.normalizar(etiqueta_esperada):
            estado = "ya estaba seleccionada" if ya_seleccionada else "quedó seleccionada tras el postback"
            raise ErrorCFE(
                f"se pidió la región '{etiqueta_esperada}' pero la página muestra "
                f"'{nombre_visible}' ({estado}). Probablemente la sesión (la cookie "
                f"reutilizada) recuerda una selección de otra región del lado del "
                f"servidor; no se confía en el resultado.")

    # -- consulta ----------------------------------------------------------

    def consultar(self, anio, mes, estado_id, municipio_id, region_id=None, region_etiqueta=None):
        """Selecciona todo y devuelve los cargos, o None si no hay publicación.

        El orden importa: año antes que mes (cambiar de año repuebla los
        meses) y estado antes que municipio.

        region_etiqueta, si se da, es el nombre visible que DEBE quedar
        seleccionado en el desplegable de división. No es opcional por
        pereza: sin esto, una sesión contaminada puede dejar seleccionada
        una división distinta a la pedida sin que nada lo note (ver
        _verificar_region).
        """
        if self.html is None:
            self.abrir()
        self.poner_anio(anio)
        self.poner_mes(mes)
        self.poner_estado(estado_id)
        self.poner_municipio(municipio_id)
        if region_id is not None:
            self.poner_region(region_id, etiqueta_esperada=region_etiqueta)
        elif self._actual(P.DD_REGION) == (None, None):
            disponibles = self.regiones_disponibles()
            if disponibles:
                self.poner_region(disponibles[0][0])
        return P.parsear_cargos(self.html)

    def opciones_de_municipio(self, estado_id, municipio_id):
        """Opciones de división que CFE ofrece para ese municipio.

        Casi siempre es una y viene preseleccionada. Pero hay municipios
        (Toluca, por ejemplo) donde el desplegable ofrece varias sin elegir
        ninguna: ahí hay que devolverlas todas, no descartar el municipio.
        """
        self.poner_estado(estado_id)
        self.poner_municipio(municipio_id)
        rid, nombre = self._actual(P.DD_REGION)
        if rid is not None:
            return [{"id": rid, "etiqueta": P.normalizar(nombre)}]
        return [{"id": v, "etiqueta": P.normalizar(t)}
                for v, t, _ in P.opciones(self.html, P.DD_REGION)]

    def horarios(self):
        if self.html is None:
            self.abrir()
        return P.parsear_horarios(self.html)
