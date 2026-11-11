# -*- coding: utf-8 -*-
"""Captura de DAC (Doméstico de Alto Consumo). La invoca actualizar_tarifas.py.

DAC no tiene ubicación: elegir año y mes basta, y la página devuelve las seis
regiones de DAC juntas. Por eso aquí no hay catálogo, representantes ni
postbacks de estado/municipio: una consulta por mes guarda seis registros.

Las guardias son las del resto de tarifas, adaptadas:
  - la tabla de cada región trae exactamente los cargos de DAC;
  - las regiones que llegan son exactamente las seis conocidas;
  - el periodo que muestra la página es el mes pedido (una sesión con otra
    selección recordada no se guarda como si fuera el mes correcto).
"""
import time

import cfe
import parser as P


periodo_esperado = cfe.periodo_esperado


def claves_del_mes(registros, anio, mes):
    pre = "DAC|"
    sufijo = f"|{anio:04d}-{mes:02d}"
    return [k for k in registros if k.startswith(pre) and k.endswith(sufijo)]


def _tablas(s):
    return P.parsear_dac(s.html)


def consultar_mes(s, anio, mes, reintentos, pausa):
    """Selecciona el mes y devuelve (tablas, intentos). Reintenta si no hay tabla."""
    s.poner_mes(mes)
    tablas = _tablas(s)
    intentos = 1
    while not tablas and intentos <= reintentos:
        time.sleep(pausa * (intentos + 1))
        s.abrir()
        s.poner_anio(anio)
        s.poner_mes(mes)
        tablas = _tablas(s)
        intentos += 1
    return tablas, intentos


def revisar(anio, mes, tablas):
    """None si la captura del mes es confiable; si no, el motivo."""
    regiones = [t["region"] for t in tablas]
    if frozenset(regiones) != cfe.REGIONES_DAC or len(regiones) != len(cfe.REGIONES_DAC):
        return (f"las regiones no son las seis esperadas: llegaron {sorted(regiones)}")
    for t in tablas:
        if not cfe.tabla_completa("DAC", t):
            return f"tabla incompleta en {t['region']}: trae {sorted(t['cargos'])}"
    esperado = periodo_esperado(anio, mes)
    if tablas[0]["periodo_cfe"] != esperado:
        return (f"se pidió {esperado} pero la página muestra {tablas[0]['periodo_cfe']}; "
                "la sesión recuerda otra selección")
    return None


def capturar(s, registros, anios, meses_filtro, rehacer, faltantes, reintentos, pausa, ahora, guardar):
    """Recorre años y meses y guarda lo nuevo. Devuelve un dict de contadores y alertas."""
    r = {"nuevos": 0, "omitidos": 0, "vacios": 0, "sospechosos": 0,
         "alertas": [], "vacios_confirmados": []}
    for anio in anios:
        # Cada año arranca desde una página recién cargada: el control de mes
        # depende del año elegido (ver control_mes en parser.py).
        s.abrir()
        s.poner_anio(anio)
        if s._actual(P.DD_ANIO)[0] != str(anio):
            print(f"   {anio}  no quedó seleccionado; se omite")
            continue
        meses = s.meses()
        if not meses:
            print(f"   {anio}  el sitio no ofrece meses; se omite")
            continue
        for mes in meses:
            if meses_filtro and mes not in meses_filtro:
                continue
            if claves_del_mes(registros, anio, mes) and (faltantes or not rehacer):
                r["omitidos"] += 1
                continue
            try:
                tablas, intentos = consultar_mes(s, anio, mes, reintentos, pausa)
            except cfe.ErrorCFE as e:
                print(f"   {anio}-{mes:02d}  ! SOSPECHOSO, no se guarda: {e}")
                r["alertas"].append(f"DAC {anio}-{mes:02d}: {e}")
                r["sospechosos"] += 1
                continue
            if not tablas:
                print(f"   {anio}-{mes:02d}  sin publicación (tras {intentos} intento(s))")
                r["vacios"] += 1
                if mes < max(meses):
                    r["vacios_confirmados"].append(f"DAC {anio}-{mes:02d} ({intentos} intentos)")
                continue
            if intentos > 1:
                print(f"   {anio}-{mes:02d}  la tabla llegó en el intento {intentos}")
            motivo = revisar(anio, mes, tablas)
            if motivo:
                print(f"   {anio}-{mes:02d}  ! SOSPECHOSO, no se guarda: {motivo}")
                r["alertas"].append(f"DAC {anio}-{mes:02d}: {motivo}")
                r["sospechosos"] += 1
                continue
            for t in tablas:
                registros[f"DAC|{t['region']}|{anio:04d}-{mes:02d}"] = {
                    "tarifa": "DAC", "region": t["region"], "anio": anio, "mes": mes,
                    "periodo_cfe": t["periodo_cfe"], "cargos": t["cargos"],
                    "unidades": t["unidades"], "conceptos": t["conceptos"],
                    "fuente": s.url, "fecha_captura": ahora(),
                }
                r["nuevos"] += 1
            nor = next(t for t in tablas if t["region"] == "NOROESTE")
            print(f"   {anio}-{mes:02d}  6 regiones  (Noroeste: "
                  + "  ".join(f"{k}={v}" for k, v in nor["cargos"].items()) + ")")
            guardar()
    return r
