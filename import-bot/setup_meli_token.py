#!/usr/bin/env python3
"""
SETUP TOKEN MERCADOLIBRE — Ejecutar UNA sola vez.
"""
import requests
import json
import os
from datetime import datetime, timedelta

APP_ID        = os.getenv("MELI_APP_ID", "YOUR_MELI_APP_ID")
CLIENT_SECRET = os.getenv("MELI_CLIENT_SECRET", "YOUR_MELI_CLIENT_SECRET")
REDIRECT_URI  = "https://httpbin.org/get"
TOKEN_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".meli_token.json")

AUTH_URL = (
    "https://auth.mercadolibre.com.ar/authorization"
    "?response_type=code"
    f"&client_id={APP_ID}"
    f"&redirect_uri={REDIRECT_URI}"
)

print("\n" + "="*60)
print("  SETUP TOKEN MERCADOLIBRE")
print("="*60)
print()
print("PASO 1: Asegurate que en tu app de MeLi el Redirect URI sea:")
print()
print("        https://httpbin.org/get")
print()
print("PASO 2: Abrí esta URL en el navegador, iniciá sesión y")
print("        hacé click en 'Permitir acceso':")
print()
print("  " + AUTH_URL)
print()
print("PASO 3: El navegador va a mostrar un JSON en httpbin.org.")
print("        Buscá la línea con 'code' y copiá el valor.")
print("        Ejemplo: TG-123456789-12345678901234")
print()
print("-"*60)

raw = input("Pegá el código acá:\n> ").strip()

# Extraer código de cualquier formato que peguen
code = raw.strip('"').strip("'")
if "code=" in raw:
    code = raw.split("code=")[1].split("&")[0].split('"')[0].strip()
elif '"code":' in raw or '"code" :' in raw:
    import re
    m = re.search(r'"code"\s*:\s*"([^"]+)"', raw)
    if m:
        code = m.group(1)

if not code or len(code) < 10:
    print(f"\n❌ No se pudo leer el código. Pegá solo el valor TG-...")
    input("Presioná Enter para cerrar...")
    exit(1)

print(f"\nIntercambiando código por tokens...")

r = requests.post(
    "https://api.mercadolibre.com/oauth/token",
    headers={
        "Accept":       "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    },
    data={
        "grant_type":    "authorization_code",
        "client_id":     APP_ID,
        "client_secret": CLIENT_SECRET,
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
    },
    timeout=15,
)

if r.status_code != 200:
    print(f"\n❌ Error HTTP {r.status_code}: {r.text[:300]}")
    input("Presioná Enter para cerrar...")
    exit(1)

data          = r.json()
access_token  = data.get("access_token", "")
refresh_token = data.get("refresh_token", "")
expires_in    = data.get("expires_in", 21600)
user_id       = data.get("user_id", "")

if not access_token:
    print(f"\n❌ Respuesta inesperada: {data}")
    input("Presioná Enter para cerrar...")
    exit(1)

expira = (datetime.now() + timedelta(seconds=expires_in - 300)).isoformat()

with open(TOKEN_FILE, "w") as f:
    json.dump({
        "token":         access_token,
        "refresh_token": refresh_token,
        "expira":        expira,
        "user_id":       str(user_id),
        "tipo":          "authorization_code",
    }, f, indent=2)

print(f"\n✅ Token guardado! Usuario MeLi ID: {user_id}")
print("¡Listo! Ahora podés correr Evaluar Productos.bat normalmente.")
input("\nPresioná Enter para cerrar...")
