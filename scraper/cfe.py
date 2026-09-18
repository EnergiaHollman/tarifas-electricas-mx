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

PAGINAS = {
    "GDMTH": "https://app.cfe.mx/Aplicaciones/CCFE/Tarifas/TarifasCRENegocio/Tarifas/GranDemandaMTH.aspx",
    # El resto del portal usa exactamente la misma mecánica; basta con
    # agregar la URL para que el scraper las capture igual.
    "GDMTO": "https://app.cfe.mx/Aplicaciones/CCFE/Tarifas/TarifasCRENegocio/Tarifas/GranDemandaMTO.aspx",
    "PDBT": "https://app.cfe.mx/Aplicaciones/CCFE/Tarifas/TarifasCRENegocio/Tarifas/PequenaDemandaBT.aspx",
}

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

        # El sitio está detrás de Imperva Incapsula: sin cookies de una sesión
        # que un navegador real ya "aprobó" (algo que requiere ejecutar
        # JavaScript, cosa que requests no hace), el sitio degrada en
        # silencio la respuesta a ciertas interacciones dinámicas, como
        # recalcular los meses al cambiar de año. La solución pragmática,
        # dado que esto corre una vez al mes: copiar el encabezado Cookie de
        # una visita real (DevTools → pestaña Red → la petición POST del
        # formulario → Headers → Request Headers → Cookie) y pasarlo aquí, ya
        # sea con este argumento o con la variable de entorno CFE_COOKIES.
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

    def poner_region(self, region_id):
        actual, _ = self._actual(P.DD_REGION)
        if actual == str(region_id):
            return
        self._postback(P.DD_REGION, {P.DD_REGION: str(region_id)})

    # -- consulta ----------------------------------------------------------

    def consultar(self, anio, mes, estado_id, municipio_id, region_id=None):
        """Selecciona todo y devuelve los cargos, o None si no hay publicación.

        El orden importa: año antes que mes (cambiar de año repuebla los
        meses) y estado antes que municipio.
        """
        if self.html is None:
            self.abrir()
        self.poner_anio(anio)
        self.poner_mes(mes)
        self.poner_estado(estado_id)
        self.poner_municipio(municipio_id)
        if region_id is not None:
            self.poner_region(region_id)
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
