#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extrae del PDF del Acuerdo el numeral 5.9 (municipios por división tarifaria).

    python3 extraer_5_9.py ACUERDO.pdf salida.json

Genera el formato que consume cruzar_catalogo.py:
    {"completo": true, "fuente": ..., "divisiones": {DIVISION: {ENTIDAD: [municipios]}}}

POR QUÉ NO BASTA CON LAS TABLAS. El 5.9 son tablas de dos columnas (Entidad |
Municipio), pero una fila larga -Oaxaca ocupa varias páginas- se parte entre
páginas y su continuación NO trae bordes: pdfplumber no la reconoce como tabla
(en el Acuerdo de 2026 la página 36 completa sale con 0 tablas). Un extractor
que solo lea tablas pierde cientos de municipios sin avisar. Aquí:

  1. se leen las tablas REALES (con encabezado, título o una entidad conocida);
  2. el texto que queda FUERA de esas tablas es continuación de la última
     entidad abierta (fila partida entre páginas);
  3. los títulos "Tabla N / División X" se leen del texto de la página, porque
     a veces quedan huérfanos al pie, sin tabla debajo (la Tabla 27, Bajío);
  4. COBERTURA INDEPENDIENTE: las palabras de lo extraído se comparan contra
     las de poppler (pdftotext) para el mismo tramo. Si falta o sobra alguna
     que no sea título, encabezado o nombre de entidad, el script falla en vez
     de entregar una tabla incompleta.

ADVERTENCIA de diseño: las zonas se asignan por la posición CENTRAL de cada
carácter, no recortando con crop(). Recortar parte las líneas de texto por la
mitad y pdfplumber las funde ("TTaemxcaazlcoilnag"); filtrar caracteres
completos no.
"""
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter

import pdfplumber

ENTIDADES = {
    "Aguascalientes", "Baja California", "Baja California Sur", "Campeche", "Chiapas", "Chihuahua",
    "Ciudad de México", "Coahuila de Zaragoza", "Colima", "Durango", "Guanajuato", "Guerrero", "Hidalgo",
    "Jalisco", "México", "Michoacán de Ocampo", "Morelos", "Nayarit", "Nuevo León", "Oaxaca", "Puebla",
    "Querétaro", "Quintana Roo", "San Luis Potosí", "Sinaloa", "Sonora", "Tabasco", "Tamaulipas",
    "Tlaxcala", "Veracruz de Ignacio de la Llave", "Yucatán", "Zacatecas",
}

# Municipios cuyo nombre oficial lleva una coma dentro: al partir por comas se
# romperían en dos. (nombre completo) -> (mitad 1, mitad 2)
COMAS_INTERNAS = {
    "Heroica Villa Tezoatlán de Segura y Luna, Cuna de la Independencia de Oaxaca":
        ("Heroica Villa Tezoatlán de Segura y Luna", "Cuna de la Independencia de Oaxaca"),
}

# Título de división: línea que EMPIEZA con "División X" (con mayúscula). Anclado
# a inicio de línea y sensible a mayúsculas: la prosa del Acuerdo usa "división"
# en minúscula a mitad de frase ("... por división tarifaria para la ...").
_TITULO_DIV = re.compile(r"^Divisi[oó]n\s+(.+?)\s*$", re.M)
# Una fila de entidad en texto libre empieza con el nombre de la entidad seguido de
# un municipio que EMPIEZA CON MAYÚSCULA (o de nada, si la entidad va sola en la
# línea). Eso descarta "Oaxaca de Juárez" (minúscula tras el nombre) y los
# municipios llamados como una entidad ("Querétaro, San Joaquín": coma).
_ENT_RE = re.compile(
    r"^(" + "|".join(re.escape(e) for e in sorted(ENTIDADES, key=len, reverse=True)) + r")(?=\s+[A-ZÁÉÍÓÚÑ]|\s*$)")


def _norm(t):
    """Clave de orden alfabético TRADICIONAL del español: la 'ch' va después de toda 'c'
    (Coahuila antes que Chihuahua), como lo listan las tablas del Acuerdo."""
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.replace("ch", "c{")        # '{' va después de 'z' en ASCII


_FIN = re.compile(r"5\.10\.|^Tabla\s+(?:4[2-9]|5\d)\b", re.M)       # lo que viene después del 5.9


def _limpiar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\n", " ")).strip()


def _palabras(texto):
    return [w for w in re.findall(r"[^\s,;]+", texto or "") if w]


def _partir_municipios(texto):
    partes = [p.strip() for p in texto.split(",") if p.strip()]
    unidos, i = [], 0
    while i < len(partes):
        for completo, (a, b) in COMAS_INTERNAS.items():
            if partes[i] == a and i + 1 < len(partes) and partes[i + 1] == b:
                unidos.append(completo)
                i += 2
                break
        else:
            unidos.append(partes[i])
            i += 1
    return unidos


def _paginas_5_9(pdf):
    inicio = fin = None
    for i, p in enumerate(pdf.pages):
        t = p.extract_text() or ""
        if inicio is None and "5.9.1" in t and "Tabla 25" in t:
            inicio = i
        if "5.10.1" in t:
            fin = i
    if inicio is None or fin is None:
        raise SystemExit("no se encontró el numeral 5.9 (5.9.1 ... 5.10.1) en el PDF")
    return inicio, fin


def _es_tabla_real(filas):
    """Una tabla del 5.9 trae título, encabezado Entidad|Municipio o una entidad conocida.
    Las 'tablas' de una celda que pdfplumber inventa sobre texto corrido NO lo son."""
    for f in filas:
        if not f or len(f) < 2:
            continue
        c0, c1 = _limpiar(f[0]), _limpiar(f[1])
        if _TITULO_DIV.search(f[0] or "") or (c0 == "Entidad" and c1 == "Municipio") or c0 in ENTIDADES:
            return True
    return False


def _texto_zona(pag, y0, y1):
    """Texto de la franja [y0, y1) tomando caracteres COMPLETOS por su posición central."""
    def dentro(o):
        if o.get("object_type") != "char":
            return True
        return y0 <= (o["top"] + o["bottom"]) / 2 < y1
    return (pag.filter(dentro).extract_text() or "").strip()


def extraer(ruta_pdf):
    pdf = pdfplumber.open(ruta_pdf)
    inicio, fin = _paginas_5_9(pdf)

    textos, orden, anomalias = {}, [], []
    division = entidad = None
    terminado = False

    def acumular(div, ent, texto):
        k = (div, ent)
        if k not in textos:
            textos[k] = ""
            orden.append(k)
        textos[k] = (textos[k] + " " + texto).strip()

    for npag in range(inicio, fin + 1):
        if terminado:
            break
        pag = pdf.pages[npag]
        reales = []
        for t in sorted(pag.find_tables(), key=lambda t: t.bbox[1]):
            filas = t.extract()
            if _es_tabla_real(filas):
                reales.append((t, filas))

        cortes, y = [], 0.0
        for t, filas in reales:
            cortes.append(("hueco", y, t.bbox[1]))
            cortes.append(("tabla", t, filas))
            y = t.bbox[3]
        cortes.append(("hueco", y, float(pag.height) + 1))

        for tipo, a, b in cortes:
            if terminado:
                break
            if tipo == "hueco":
                if b - a < 2:
                    continue
                texto = _texto_zona(pag, a, b)
                if not texto:
                    continue
                if _FIN.search(texto):
                    terminado = True
                    break
                m = _TITULO_DIV.search(texto)
                if m:                                  # título huérfano: "Tabla 27 / División Bajío"
                    division = _limpiar(m.group(1))
                    entidad = None
                    continue
                if division is None:
                    continue                                        # prosa previa al 5.9.1
                for linea in texto.split("\n"):
                    linea = linea.strip()
                    if not linea:
                        continue
                    m = _ENT_RE.match(linea)
                    # Una entidad nueva dentro de una división va en orden alfabético estricto
                    # (las tablas del Acuerdo lo respetan); eso descarta falsos positivos.
                    if m and (entidad is None or _norm(m.group(1)) > _norm(entidad)):
                        entidad = m.group(1)
                        acumular(division, entidad, linea[m.end():].strip())
                    elif entidad is not None:
                        acumular(division, entidad, linea)          # continuación de una fila partida
                continue

            # --- una tabla real ---
            filas = b
            if re.match(r"Tabla\s+(?:4[2-9]|5\d)\b", _limpiar(filas[0][0] if filas and filas[0] else "")):
                terminado = True
                break
            for fila in filas:
                if not fila or len(fila) < 2:
                    continue
                c0, c1 = _limpiar(fila[0]), _limpiar(fila[1])
                m = _TITULO_DIV.search(fila[0] or "")
                if m:
                    division = _limpiar(m.group(1))
                    entidad = None
                    continue
                if c0 == "Entidad" and c1 == "Municipio":
                    continue
                if not c0 and not c1:
                    continue
                if division is None:
                    anomalias.append(f"p.{npag+1}: fila antes de cualquier título: {c0!r} | {c1[:40]!r}")
                    continue
                if c0 in ENTIDADES:
                    entidad = c0
                    acumular(division, entidad, c1)
                elif not c0 and entidad is not None:
                    acumular(division, entidad, c1)         # fila partida: la entidad sigue abierta
                else:
                    anomalias.append(f"p.{npag+1}: fila no reconocida en {division}: {c0!r} | {c1[:40]!r}")

    divisiones = {}
    for (div, ent) in orden:
        munis = _partir_municipios(textos[(div, ent)])
        vistos, unicos = set(), []
        for m in munis:
            if m not in vistos:
                vistos.add(m)
                unicos.append(m)
        divisiones.setdefault(div, {})[ent] = unicos
    return divisiones, anomalias


def _texto_poppler(ruta_pdf, desde, hasta):
    out = subprocess.run(["pdftotext", "-f", str(desde), "-l", str(hasta), "-raw", ruta_pdf, "-"],
                         capture_output=True, text=True, check=True).stdout
    i = out.find("Tabla 25")
    j = out.find("5.10. Correspondencias")
    if i < 0 or j < 0:
        raise SystemExit("poppler no encontró 'Tabla 25' / '5.10. Correspondencias' para la cobertura")
    return out[i:j]


def cobertura(ruta_pdf, divisiones):
    """Diferencia de palabras entre poppler (verdad independiente) y lo extraído.

    Devuelve (faltan, sobran): palabras que el PDF tiene y no capturamos, y al revés.
    Se descuentan títulos, encabezados y los nombres de entidad.
    """
    pdf = pdfplumber.open(ruta_pdf)
    ini, fin = _paginas_5_9(pdf)
    ref = Counter(_palabras(_texto_poppler(ruta_pdf, ini + 1, fin + 1)))

    capturadas = Counter()
    for d, por_ent in divisiones.items():
        capturadas.update(_palabras(f"Divisi\u00f3n {d}"))
        for ent, munis in por_ent.items():
            capturadas.update(_palabras(ent))
            for m in munis:
                capturadas.update(_palabras(m))
    # Ruido estructural: "Tabla N", "Entidad", "Municipio" (puede repetirse en tablas partidas).
    for n in range(25, 25 + len(divisiones)):
        capturadas.update(["Tabla", str(n)])
    for w in ("Entidad", "Municipio"):
        ref.pop(w, None)
        capturadas.pop(w, None)
    faltan = ref - capturadas
    sobran = capturadas - ref
    return faltan, sobran


def validar(divisiones):
    problemas = []
    for d, por_ent in divisiones.items():
        ents = list(por_ent)
        for a, b in zip(ents, ents[1:]):
            if not _norm(a) < _norm(b):
                problemas.append(f"{d}: las entidades no van en orden alfabético ({a!r} antes de {b!r})")
    if len(divisiones) != 17:
        problemas.append(f"se esperaban 17 divisiones y salieron {len(divisiones)}: {sorted(divisiones)}")
    for d, por_ent in divisiones.items():
        for e in por_ent:
            if e not in ENTIDADES:
                problemas.append(f"entidad fuera de la lista oficial en {d}: {e!r}")
    return problemas


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    ruta = sys.argv[1]
    divs, anomalias = extraer(ruta)
    faltan, sobran = cobertura(ruta, divs)
    problemas = validar(divs) + anomalias
    total = sum(len(m) for d in divs.values() for m in d.values())
    print(f"{len(divs)} divisiones, {total} asignaciones municipio-división")
    for d, por_ent in divs.items():
        print(f"  {d:<26} {sum(len(m) for m in por_ent.values()):>4} municipios en {len(por_ent)} entidad(es)")
    print(f"\nCOBERTURA contra poppler: faltan {sum(faltan.values())} palabra(s), sobran {sum(sobran.values())}")
    if faltan:
        print("  faltan:", dict(faltan.most_common(15)))
        problemas.append(f"cobertura incompleta: faltan {sum(faltan.values())} palabra(s) del PDF")
    if sobran:
        print("  sobran:", dict(sobran.most_common(15)))
        problemas.append(f"se capturaron {sum(sobran.values())} palabra(s) que el PDF no tiene")
    if problemas:
        print("\nANOMALÍAS:")
        for p in problemas:
            print("  -", p)
    json.dump({"completo": not problemas, "fuente": "Acuerdo CNE CT/11.SE/8-2025, numeral 5.9 (2026)",
               "divisiones": divs}, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nguardado en {sys.argv[2]}  (completo={not problemas})")
    sys.exit(1 if problemas else 0)
