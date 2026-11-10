# -*- coding: utf-8 -*-
"""Captura de las tarifas domésticas (1, 1A a 1F). La invoca actualizar_tarifas.py.

No piden ubicación: el precio es nacional y se guarda bajo la región NACIONAL.
Las 1A a 1F dependen de la temporada de verano de la localidad, y CFE la pide
como "el mes en que comienza el verano" (febrero a mayo); el verano dura seis
meses seguidos. En vez de capturar los cuatro inicios, se piden dos (febrero y
mayo), que bastan para obtener las dos temporadas de cualquier mes: se comprobó
contra marzo y abril en los meses donde cambia el régimen (12 de 12).

Por cada mes se guarda UN registro con las temporadas que existan: ene, nov y
dic solo tienen fuera de verano; may, jun y jul solo verano. La 1 no tiene
temporadas y guarda cargos y escalones directamente.

Guardias (un mes que falla alguna NO se guarda):
  - el periodo que muestra la página es el mes pedido, y el inicio de verano
    seleccionado es el pedido (una sesión que recuerda otra selección);
  - la temporada de cada tabla es la que da la regla [inicio, inicio+5];
  - los cargos son exactamente los de esa tarifa y temporada;
  - los límites de los escalones son contiguos y el excedente no tiene tope;
  - si dos inicios dan la misma temporada, las tablas son idénticas;
  - un texto de CFE que el parser no reconoce.
"""
import time

import cfe
import parser as P


def periodo_esperado(anio, mes):
    return f"{P.MESES[mes - 1][:3]}-{str(anio)[-2:]}"


def clave(tarifa, anio, mes):
    return f"{tarifa}|{cfe.REGION_NACIONAL}|{anio:04d}-{mes:02d}"


def temporada_esperada(mes, inicio):
    """Regla de CFE: el verano son seis meses seguidos desde el mes de inicio."""
    return "verano" if inicio <= mes <= inicio + 5 else "fuera_verano"


def _leer(s, mes, inicio):
    if inicio is not None:
        s.poner_inicio_verano(inicio)
    s.forzar_mes(mes)
    return P.parsear_domestica(s.html)


def consultar_mes(s, anio, mes, inicio, reintentos, pausa):
    """(tabla, intentos). Reintenta, reabriendo la página, si responde sin tabla."""
    tabla = _leer(s, mes, inicio)
    intentos = 1
    while tabla is None and intentos <= reintentos:
        time.sleep(pausa * (intentos + 1))
        s.abrir()
        s.poner_anio(anio)
        tabla = _leer(s, mes, inicio)
        intentos += 1
    return tabla, intentos


def revisar_escalones(escalones):
    """None si los límites son contiguos y solo el excedente queda sin tope."""
    previo = 0
    for i, e in enumerate(escalones):
        if e["desde_kwh"] != previo:
            return f"el escalón {e['nombre']} empieza en {e['desde_kwh']} y se esperaba {previo}"
        ultimo = i == len(escalones) - 1
        if ultimo != (e["hasta_kwh"] is None):
            return f"solo el excedente debe quedar sin tope (escalón {e['nombre']})"
        if not ultimo:
            if e["hasta_kwh"] <= e["desde_kwh"]:
                return f"el escalón {e['nombre']} no tiene tamaño positivo"
            previo = e["hasta_kwh"]
    return None


def _bloque(t):
    return {"cargos": t["cargos"], "unidades": t["unidades"],
            "escalones": t["escalones"], "conceptos": t["conceptos"]}


def armar(tarifa, anio, mes, tablas_por_inicio, ahora, url):
    """(registro, None) o (None, motivo). tablas_por_inicio: {inicio o None: tabla}."""
    estacional = cfe.TARIFAS[tarifa]["temporadas"]
    esperado = periodo_esperado(anio, mes)
    por_temporada = {}
    for inicio, t in tablas_por_inicio.items():
        if t["periodo_cfe"] != esperado:
            return None, (f"se pidió {esperado} pero la página muestra {t['periodo_cfe']}; "
                          "la sesión recuerda otra selección")
        if estacional:
            if t["inicio_verano"] != str(inicio):
                return None, (f"se pidió inicio de verano {inicio} pero la página tiene "
                              f"{t['inicio_verano']}")
            regla = temporada_esperada(mes, inicio)
            if t["temporada"] != regla:
                return None, (f"con inicio {inicio} y mes {mes} la regla del verano da {regla} "
                              f"pero la página muestra {t['temporada']}")
        elif t["temporada"] is not None:
            return None, f"{tarifa} no tiene temporadas y la página muestra {t['temporada']}"
        if not cfe.tabla_completa(tarifa, t):
            return None, f"cargos distintos a los de {tarifa} ({t['temporada']}): trae {sorted(t['cargos'])}"
        motivo = revisar_escalones(t["escalones"])
        if motivo:
            return None, motivo
        if t["minimo_mensual_kwh"] is None:
            return None, "no se encontró el mínimo mensual"
        previa = por_temporada.get(t["temporada"])
        if previa is not None and _bloque(previa) != _bloque(t):
            return None, (f"dos inicios de verano dan la misma temporada ({t['temporada']}) "
                          "con tablas distintas")
        por_temporada[t["temporada"]] = t
    if len({t["minimo_mensual_kwh"] for t in por_temporada.values()}) != 1:
        return None, "el mínimo mensual difiere entre temporadas"
    registro = {"tarifa": tarifa, "region": cfe.REGION_NACIONAL, "anio": anio, "mes": mes,
                "periodo_cfe": esperado,
                "minimo_mensual_kwh": next(iter(por_temporada.values()))["minimo_mensual_kwh"],
                "fuente": url, "fecha_captura": ahora()}
    if estacional:
        registro["temporadas"] = {n: _bloque(por_temporada[n])
                                  for n in ("verano", "fuera_verano") if n in por_temporada}
    else:
        registro.update(_bloque(por_temporada[None]))
    return registro, None


def capturar(s, registros, anios, meses_filtro, rehacer, faltantes, reintentos, pausa, ahora, guardar,
             tarifa):
    r = {"nuevos": 0, "omitidos": 0, "vacios": 0, "sospechosos": 0,
         "alertas": [], "vacios_confirmados": []}
    inicios = cfe.INICIOS_VERANO if cfe.TARIFAS[tarifa]["temporadas"] else (None,)

    def alerta(anio, mes, texto):
        print(f"   {anio}-{mes:02d}  ! SOSPECHOSO, no se guarda: {texto}")
        r["alertas"].append(f"{tarifa} {anio}-{mes:02d}: {texto}")
        r["sospechosos"] += 1

    for anio in anios:
        # Cada año arranca desde una página recién cargada.
        s.abrir()
        s.poner_anio(anio)
        if s._actual(P.DD_ANIO)[0] != str(anio):
            print(f"   {anio}  no quedó seleccionado; se omite")
            continue
        meses = s.meses()
        if not meses:
            print(f"   {anio}  el sitio no ofrece meses; se omite")
            continue
        pendientes = []
        for mes in meses:
            if meses_filtro and mes not in meses_filtro:
                continue
            if clave(tarifa, anio, mes) in registros and (faltantes or not rehacer):
                r["omitidos"] += 1
                continue
            pendientes.append(mes)

        # Una pasada por inicio de verano: el inicio se cambia una sola vez.
        tablas = {mes: {} for mes in pendientes}
        fallidos = set()
        for inicio in inicios:
            for mes in pendientes:
                if mes in fallidos:
                    continue
                try:
                    t, intentos = consultar_mes(s, anio, mes, inicio, reintentos, pausa)
                except (cfe.ErrorCFE, P.ErrorParseo) as e:
                    alerta(anio, mes, str(e))
                    fallidos.add(mes)
                    continue
                if t is None:
                    tablas[mes][inicio] = None
                    continue
                if intentos > 1:
                    print(f"   {anio}-{mes:02d}  la tabla llegó en el intento {intentos}")
                tablas[mes][inicio] = t

        for mes in pendientes:
            if mes in fallidos:
                continue
            vistas = tablas[mes]
            if all(t is None for t in vistas.values()):
                print(f"   {anio}-{mes:02d}  sin publicación")
                r["vacios"] += 1
                if mes < max(meses):
                    r["vacios_confirmados"].append(f"{tarifa} {anio}-{mes:02d}")
                continue
            if any(t is None for t in vistas.values()):
                faltan = [i for i, t in vistas.items() if t is None]
                alerta(anio, mes, f"solo respondió uno de los inicios de verano (sin tabla con {faltan})")
                continue
            registro, motivo = armar(tarifa, anio, mes, vistas, ahora, s.url)
            if motivo:
                alerta(anio, mes, motivo)
                continue
            registros[clave(tarifa, anio, mes)] = registro
            r["nuevos"] += 1
            if "temporadas" in registro:
                det = "  ".join(f"{n}: " + "/".join(str(v) for v in b["cargos"].values())
                                for n, b in registro["temporadas"].items())
            else:
                det = "/".join(str(v) for v in registro["cargos"].values())
            print(f"   {anio}-{mes:02d}  {det}")
        guardar()
    return r
