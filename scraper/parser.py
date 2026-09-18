# -*- coding: utf-8 -*-
"""Parseo del HTML del portal de tarifas de CFE.

Sin red, sin estado: funciones puras HTML -> dicts. Todo lo que se puede
romper cuando CFE rediseñe el sitio vive aquí y se prueba con
`test_parser.py` contra la muestra guardada en `muestra/`.
"""
import re
import unicodedata

from bs4 import BeautifulSoup

# Nombres de los controles del formulario WebForms.
DD_ANIO = "ctl00$ContentPlaceHolder1$Fecha$ddAnio"
DD_MES = "ctl00$ContentPlaceHolder1$Fecha2$ddMes"
DD_ESTADO = "ctl00$ContentPlaceHolder1$EdoMpoDiv$ddEstado"
DD_MUNICIPIO = "ctl00$ContentPlaceHolder1$EdoMpoDiv$ddMunicipio"
DD_REGION = "ctl00$ContentPlaceHolder1$EdoMpoDiv$ddDivision"

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
         "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]


def _sopa(html):
    return html if isinstance(html, BeautifulSoup) else BeautifulSoup(html, "lxml")


def normalizar(texto):
    """Mayúsculas sin acentos ni espacios redundantes. Para comparar nombres."""
    t = unicodedata.normalize("NFD", (texto or "").strip())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).upper()


def _clave(texto):
    """Nombre de concepto -> clave de diccionario: 'Distribución' -> 'distribucion'."""
    t = normalizar(texto).lower()
    t = re.sub(r"\(.*?\)", "", t)
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t


# --------------------------------------------------------------------------
# Formulario
# --------------------------------------------------------------------------

def campos_formulario(html):
    """Todos los campos que hay que reenviar en un postback.

    Incluye los hidden de ASP.NET (__VIEWSTATE, __EVENTVALIDATION, ...), los
    hidden propios de la página (hdAnio, hdMes) y el valor seleccionado de cada
    <select>. Sin esto el servidor rechaza el postback.
    """
    s = _sopa(html)
    datos = {}
    for inp in s.select("input[type=hidden]"):
        nombre = inp.get("name")
        if nombre:
            datos[nombre] = inp.get("value", "")
    for sel in s.find_all("select"):
        nombre = sel.get("name")
        if not nombre:
            continue
        opcion = sel.find("option", selected=True) or sel.find("option")
        datos[nombre] = opcion.get("value", "") if opcion else ""
    return datos


def opciones(html, nombre_select):
    """[(valor, texto, seleccionada)] de un <select>, sin el placeholder."""
    s = _sopa(html)
    sel = s.find("select", attrs={"name": nombre_select})
    if sel is None:
        return []
    fuera = []
    for op in sel.find_all("option"):
        valor = op.get("value", "")
        texto = op.get_text(strip=True)
        if valor in ("", "0") or texto.startswith("--"):
            continue
        fuera.append((valor, texto, op.has_attr("selected")))
    return fuera


def seleccionado(html, nombre_select):
    """(valor, texto) de la opción activa, o (None, None)."""
    s = _sopa(html)
    sel = s.find("select", attrs={"name": nombre_select})
    if sel is None:
        return None, None
    op = sel.find("option", selected=True)
    if op is None:
        return None, None
    valor = op.get("value", "")
    if valor in ("", "0"):
        return None, None
    return valor, op.get_text(strip=True)


# --------------------------------------------------------------------------
# Tabla de cargos
# --------------------------------------------------------------------------

def _numero(texto):
    t = (texto or "").replace(",", "").replace("$", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def parsear_cargos(html):
    """Lee la tabla de resultados.

    Devuelve None si la página no trae resultados (faltan selecciones o CFE no
    publicó ese mes). Si los trae:

        {"tarifa": "GDMTH", "region": "Noroeste", "periodo_cfe": "MAR-26",
         "conceptos": [{"int_horario", "cargo", "unidades", "valor"}, ...],
         "cargos":   {"fijo": 197.77, "base": 0.9715, ...},
         "unidades": {"fijo": "$/mes", ...}}

    `conceptos` es la lectura literal de la tabla y sirve para cualquier
    tarifa; `cargos` es el atajo normalizado.
    """
    todas = parsear_todas(html)
    return todas[0] if todas else None


def parsear_todas(html):
    """Todas las tablas de resultados de la página.

    Normalmente hay una. Pero hay municipios que CFE atiende con dos
    divisiones a la vez (el desplegable los etiqueta "Bajío y Golfo Centro",
    por ejemplo) y entonces la página devuelve una tabla por división.
    """
    s = _sopa(html)
    return [r for r in (_parsear_tabla(t) for t in
                        s.find_all("table", class_=lambda c: c and "table-striped" in c))
            if r is not None]


def _parsear_tabla(tabla):
    filas = tabla.find_all("tr")
    if len(filas) < 2:
        return None

    encabezados = [c.get_text(strip=True) for c in filas[0].find_all(["th", "td"])]
    periodo_cfe = encabezados[-1] if encabezados else None

    titulo = tabla.find_previous(["h3", "h2"])
    region = titulo.get_text(strip=True) if titulo else None

    tarifa = None
    conceptos = []
    for fila in filas[1:]:
        celdas = fila.find_all(["th", "td"])
        if len(celdas) < 4:
            continue
        # Las celdas con rowspan (tarifa y descripción) solo aparecen en la
        # primera fila; por eso se lee siempre desde el final.
        valor = _numero(celdas[-1].get_text(strip=True))
        unidades = celdas[-2].get_text(strip=True)
        cargo = celdas[-3].get_text(strip=True)
        int_horario = celdas[-4].get_text(strip=True)
        if valor is None:
            continue
        if tarifa is None and len(celdas) > 4:
            tarifa = celdas[0].get_text(strip=True)
        conceptos.append({"int_horario": int_horario, "cargo": cargo,
                          "unidades": unidades, "valor": valor})

    if not conceptos:
        return None

    cargos, unidades_norm = {}, {}
    for c in conceptos:
        # En las filas de energía el concepto es el intervalo horario
        # (Base/Intermedia/Punta); en las demás, el nombre del cargo.
        base = c["int_horario"] if _clave(c["cargo"]).startswith("variable") else c["cargo"]
        k = _clave(base)
        if k and k != "-":
            cargos[k] = c["valor"]
            unidades_norm[k] = c["unidades"]

    return {"tarifa": tarifa, "region": region, "periodo_cfe": periodo_cfe,
            "conceptos": conceptos, "cargos": cargos, "unidades": unidades_norm}


# --------------------------------------------------------------------------
# Tablas de horarios
# --------------------------------------------------------------------------

_RANGO = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")


def _rangos(celda):
    fuera = []
    for h1, m1, h2, m2 in _RANGO.findall(celda.get_text(" ", strip=True)):
        fuera.append([int(h1) * 60 + int(m1), int(h2) * 60 + int(m2)])
    return fuera


_TIPO_DIA = {"lunes a viernes": "habil", "sábado": "sabado", "sabado": "sabado",
             "domingo y festivo": "domingo"}


def _tabla_horario(tabla):
    """Una tabla de horarios -> {'habil': {'base': [[ini,fin]], ...}, ...}."""
    fuera = {}
    filas = tabla.find_all("tr")
    for fila in filas[1:]:
        celdas = fila.find_all(["th", "td"])
        if len(celdas) < 4:
            continue
        etiqueta = normalizar(celdas[0].get_text(strip=True)).lower()
        tipo = None
        for k, v in _TIPO_DIA.items():
            if normalizar(k).lower() == etiqueta:
                tipo = v
        if tipo is None:
            continue
        fuera[tipo] = {"base": _rangos(celdas[1]),
                       "intermedia": _rangos(celdas[2]),
                       "punta": _rangos(celdas[3])}
    return fuera


def parsear_horarios(html):
    """Las seis tablas de horarios, agrupadas por zona y temporada.

    La página las publica siempre completas, independientemente de la región
    consultada. Antes de cada par viene el nombre de la zona y antes de cada
    tabla el texto que define su temporada; ambos se conservan literales.
    """
    s = _sopa(html)
    tablas = [t for t in s.find_all("table")
              if t.get("border") == "1" and "table" in (t.get("class") or [])]
    zonas, zona_actual = {}, None
    for tabla in tablas:
        # Texto que precede a la tabla: trae la vigencia y, en la primera de
        # cada zona, también el nombre de la zona.
        previo = ""
        nodo = tabla
        while nodo is not None and len(previo) < 400:
            nodo = nodo.previous_element
            if isinstance(nodo, str):
                previo = nodo.strip() + " " + previo
        previo = re.sub(r"\s+", " ", previo).strip()

        # La vigencia es el último "Del ..." pegado a la tabla. El nombre de la
        # zona solo aparece antes de la primera tabla de cada par, y se exige
        # mayúscula inicial para no confundirlo con la frase "...se definen en
        # cada una de las regiones tarifarias..." que va en el texto corrido.
        vig = re.findall(r"Del\s+[^.]{5,200}$", previo)
        vigencia = vig[-1].strip() if vig else ""
        zon = re.findall(r"Regi(?:ón|ones)\s+[A-ZÁÉÍÓÚÑ][^.]{0,140}?(?=Del\s)", previo)
        if zon:
            zona_actual = re.sub(r"\s+", " ", zon[-1]).strip()
        if zona_actual is None:
            continue

        entrada = zonas.setdefault(zona_actual, {"zona": zona_actual, "temporadas": []})
        entrada["temporadas"].append({"vigencia": vigencia,
                                      "regla": regla_vigencia(vigencia),
                                      "dias": _tabla_horario(tabla)})

    # La primera tabla de cada zona es verano; la segunda, invierno.
    fuera = {}
    for zona, datos in zonas.items():
        temporadas = {}
        for nombre, t in zip(("verano", "invierno"), datos["temporadas"]):
            temporadas[nombre] = t
        fuera[zona] = {"zona": zona, "regiones": _regiones_de_zona(zona),
                       "temporadas": temporadas}
    return fuera


_MES_NUM = {m: i + 1 for i, m in enumerate(MESES)}
_ORDINAL = {"PRIMER": 1, "PRIMERO": 1, "SEGUNDO": 2, "TERCER": 3, "TERCERO": 3,
            "CUARTO": 4}
# weekday() de Python: lunes 0 ... domingo 6
_DIA_NUM = {"LUNES": 0, "MARTES": 1, "MIERCOLES": 2, "JUEVES": 3, "VIERNES": 4,
            "SABADO": 5, "DOMINGO": 6}


def _extremo(texto):
    """'sábado anterior al último domingo de octubre' -> regla calculable.

    Devuelve None si la redacción no se reconoce; en ese caso la API reporta
    la temporada como desconocida en vez de inventarla.
    """
    t = normalizar(texto)
    desplazamiento = 0
    m = re.match(r"^(LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO)\s+ANTERIOR AL\s+(.*)$", t)
    if m:
        desplazamiento = -1
        t = m.group(2)
    m = re.match(r"^(\d{1,2})\s*[ºO°]?\s+DE\s+([A-Z]+)$", t)
    if m and m.group(2) in _MES_NUM:
        return {"tipo": "fijo", "mes": _MES_NUM[m.group(2)], "dia": int(m.group(1)),
                "desplazamiento": desplazamiento}
    m = re.match(r"^ULTIMO\s+([A-Z]+)\s+DE\s+([A-Z]+)$", t)
    if m and m.group(1) in _DIA_NUM and m.group(2) in _MES_NUM:
        return {"tipo": "ultimo_dia_semana", "mes": _MES_NUM[m.group(2)],
                "dia_semana": _DIA_NUM[m.group(1)], "desplazamiento": desplazamiento}
    m = re.match(r"^([A-Z]+)\s+([A-Z]+)\s+DE\s+([A-Z]+)$", t)
    if m and m.group(1) in _ORDINAL and m.group(2) in _DIA_NUM and m.group(3) in _MES_NUM:
        return {"tipo": "n_dia_semana", "n": _ORDINAL[m.group(1)],
                "mes": _MES_NUM[m.group(3)], "dia_semana": _DIA_NUM[m.group(2)],
                "desplazamiento": desplazamiento}
    return None


def regla_vigencia(texto):
    """'Del X al Y' -> {'inicio': regla, 'fin': regla} o None."""
    t = re.sub(r"^\s*Del\s+", "", (texto or "").strip(), flags=re.I)
    if " al " not in t:
        return None
    ini, fin = t.split(" al ", 1)
    r_ini, r_fin = _extremo(ini), _extremo(fin)
    if r_ini is None or r_fin is None:
        return None
    return {"inicio": r_ini, "fin": r_fin}


def separar_regiones(etiqueta):
    """'Bajío y Golfo Centro' -> ['BAJIO', 'GOLFO CENTRO'].

    Algunos municipios los atienden dos divisiones y CFE los etiqueta así en
    el desplegable. Ninguna división real lleva " y " en el nombre, de modo
    que el corte es seguro.
    """
    t = normalizar(etiqueta)
    return [p.strip() for p in re.split(r"\s+Y\s+", t) if p.strip()] or [t]


def _regiones_de_zona(zona):
    """'Regiones Central, Noreste, ...' -> ['CENTRAL', 'NORESTE', ...]."""
    t = re.sub(r"^Regi(?:ón|ones)\s+", "", zona, flags=re.I)
    partes = re.split(r",| y ", t)
    return [normalizar(p) for p in partes if normalizar(p)]
