# -*- coding: utf-8 -*-
"""Arma un bundle de CA que incluya los intermedios que el servidor no manda.

El servidor de CFE no envía la cadena completa de certificados. Los
navegadores y Windows lo resuelven solos descargando el intermedio desde la
extensión AIA del certificado; Python no. Por eso en Windows funciona y en un
runner de Linux falla con CERTIFICATE_VERIFY_FAILED.

Esto hace esa misma descarga: se conecta, lee la extensión "CA Issuers",
baja los intermedios que falten y los pega al bundle de certifi.

    python3 preparar_tls.py                 # imprime la ruta del bundle
    python3 preparar_tls.py --github-env    # además lo exporta en Actions

Después basta con REQUESTS_CA_BUNDLE apuntando ahí: requests lo respeta solo.
No se baja la verificación en ningún momento; solo se completa la cadena.
"""
import argparse
import os
import pathlib
import socket
import ssl
import sys
import urllib.request

import certifi
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

HOST_POR_OMISION = "app.cfe.mx"
DESTINO = pathlib.Path(__file__).parent / "ca_bundle.pem"


def hoja(host, puerto=443, timeout=30):
    """Certificado que presenta el servidor. Sin verificar: solo lo leemos."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, puerto), timeout=timeout) as s:
        with ctx.wrap_socket(s, server_hostname=host) as ss:
            return x509.load_der_x509_certificate(ss.getpeercert(binary_form=True))


def url_emisor(cert):
    """URL del certificado emisor, de la extensión Authority Information Access."""
    try:
        aia = cert.extensions.get_extension_for_class(x509.AuthorityInformationAccess).value
    except x509.ExtensionNotFound:
        return None
    for acceso in aia:
        if acceso.access_method == x509.oid.AuthorityInformationAccessOID.CA_ISSUERS:
            return acceso.access_location.value
    return None


def descargar(url, timeout=30):
    """Los emisores suelen publicarse en DER; certifi necesita PEM."""
    with urllib.request.urlopen(url, timeout=timeout) as r:
        datos = r.read()
    try:
        return x509.load_der_x509_certificate(datos)
    except ValueError:
        return x509.load_pem_x509_certificate(datos)


def nombre(cert_nombre):
    try:
        return cert_nombre.rfc4514_string()
    except Exception:                          # noqa: BLE001
        return str(cert_nombre)


def cadena_faltante(host, maximo=5):
    """Sube por la cadena hasta llegar a una raíz o agotar los enlaces AIA."""
    cert = hoja(host)
    print(f"  certificado del servidor: {nombre(cert.subject)}")
    print(f"  emitido por:              {nombre(cert.issuer)}")
    fuera = []
    for _ in range(maximo):
        if cert.issuer == cert.subject:      # autofirmado: es la raíz
            break
        url = url_emisor(cert)
        if not url:
            print("  sin enlace AIA: no hay más intermedios que bajar")
            break
        print(f"  bajando: {url}")
        cert = descargar(url)
        print(f"    -> {nombre(cert.subject)}")
        fuera.append(cert)
    return fuera


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=HOST_POR_OMISION)
    ap.add_argument("--github-env", action="store_true",
                    help="exporta REQUESTS_CA_BUNDLE en GitHub Actions")
    args = ap.parse_args()

    print(f"Completando la cadena de {args.host}")
    try:
        intermedios = cadena_faltante(args.host)
    except Exception as e:                     # noqa: BLE001
        sys.exit(f"no se pudo leer la cadena: {e}")

    base = pathlib.Path(certifi.where()).read_bytes()
    extra = b"".join(c.public_bytes(Encoding.PEM) for c in intermedios)
    DESTINO.write_bytes(base + b"\n" + extra)
    print(f"  {len(intermedios)} intermedio(s) agregados a {DESTINO}")

    # Comprobación real: si esto pasa, el scraper también va a poder.
    import requests
    try:
        r = requests.get(f"https://{args.host}", verify=str(DESTINO), timeout=30)
        print(f"  verificación TLS correcta (HTTP {r.status_code})")
    except requests.exceptions.SSLError as e:
        print(f"\n  LA VERIFICACIÓN SIGUE FALLANDO: {e}\n")
        print("  Completar la cadena no bastó. Las causas posibles son dos:\n"
              "   - La raíz que firma el certificado no está en el almacén de\n"
              "     confianza estándar (pasa con algunas CA de gobierno).\n"
              "   - Hay un proxy TLS en medio que sustituye el certificado.\n\n"
              "  Revisa arriba quién emite el certificado. Si es una CA legítima\n"
              "  pero poco común, la salida rápida es correr el scraper con\n"
              "  --inseguro, que salta la verificación. Los datos son públicos y\n"
              "  de solo lectura, así que el riesgo es bajo, pero no es la\n"
              "  solución bonita.")
        sys.exit(1)

    if args.github_env and os.environ.get("GITHUB_ENV"):
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as f:
            f.write(f"REQUESTS_CA_BUNDLE={DESTINO}\n")
        print("  exportado REQUESTS_CA_BUNDLE")
    else:
        print(f"\nExporta la variable antes de correr el scraper:\n"
              f"  Linux/Mac:  export REQUESTS_CA_BUNDLE={DESTINO}\n"
              f"  Windows:    set REQUESTS_CA_BUNDLE={DESTINO}")


if __name__ == "__main__":
    main()
