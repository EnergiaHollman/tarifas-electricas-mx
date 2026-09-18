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

# El User-Agent y las cabeceras que siguen imitan un navegador real. Se probó
# primero con un User-Agent que se identificaba como bot (más honesto para un
# acceso mensual de solo lectura) y el sitio dejaba de recalcular el
# desplegable de meses al cambiar de año, aunque la carga inicial funcionaba
# igual para ambos casos: algo en el servidor distingue por cabeceras, no
# por el contenido del formulario. Con cabeceras de navegador el mismo
# postback sí funciona.
AGENTE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

CABECERAS_COMUNES = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


class ErrorCFE(RuntimeError):
    pass


class SesionCFE:
    """Una sesión contra una página de tarifas."""

    def __init__(self, tarifa="GDMTH", pausa=1.5, timeout=45, reintentos=3,
                 verificar_tls=None):
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

    # -- transporte --------------------------------------------------------

    def _pedir(self, metodo, **kw):
        cabeceras = kw.pop("headers", {})
        cabeceras.setdefault("Sec-Fetch-Site", "same-origin")
        cabeceras.setdefault("Sec-Fetch-Mode", "navigate" if metodo == "GET" else "same-origin")
        cabeceras.setdefault("Sec-Fetch-Dest", "document" if metodo == "GET" else "empty")
        if metodo == "POST":
            cabeceras.setdefault("Origin", "https://app.cfe.mx")
        ultimo = None
        for intento in range(self.reintentos):
            try:
                r = self.s.request(metodo, self.url, timeout=self.timeout,
                                   verify=self.verificar, headers=cabeceras, **kw)
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
        return P.seleccionado(self.html, control)

    def anios(self):
        if self.html is None:
            self.abrir()
        return [int(v) for v, _, _ in P.opciones(self.html, P.DD_ANIO)]

    def meses(self):
        """Meses publicados para el año seleccionado.

        En el año en curso CFE solo lista los meses ya publicados, así que hay
        que leerlos en vez de asumir 12.
        """
        return [int(v) for v, _, _ in P.opciones(self.html, P.DD_MES)]

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
        actual, _ = self._actual(P.DD_MES)
        if actual == str(mes):
            return
        # Enviar un mes que ya no está entre las opciones hace que el
        # servidor responda 500 (el __EVENTVALIDATION lo rechaza). Puede
        # pasar si el año cambió y el mes pedido ya no aplica.
        ofrecidos = [v for v, _, _ in P.opciones(self.html, P.DD_MES)]
        if str(mes) not in ofrecidos:
            raise ErrorCFE(f"mes {mes} no está entre los que ofrece la página "
                           f"ahora mismo ({ofrecidos}); hay que revisar meses() "
                           f"después del año antes de pedir un mes")
        self._postback(P.DD_MES, {P.DD_MES: str(mes)})

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
