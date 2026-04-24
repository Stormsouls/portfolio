#!/usr/bin/env python3
"""
PUBLICADOR AUTOMÁTICO — MERCADOLIBRE ARGENTINA
Lee el último reporte de oportunidades (CSV generado por evaluador_productos.py)
y publica los productos viables en MercadoLibre Argentina.

Modo interactivo: muestra cada producto, permite confirmar, ajustar precio y publicar.
Guarda un log de todo lo publicado en publicaciones_meli.csv.

Requisitos:
  - Token MeLi en .meli_token.json (corré setup_meli_token.py si no lo tenés)
  - Reporte CSV en la carpeta del proyecto (generado por evaluador_productos.py)
"""

import requests
import json
import csv
import os
import re
import time
import glob
from datetime import datetime

# ============================================================
# CONFIGURACIÓN
# ============================================================
MELI_APP_ID        = os.getenv("MELI_APP_ID", "YOUR_MELI_APP_ID")
MELI_CLIENT_SECRET = os.getenv("MELI_CLIENT_SECRET", "YOUR_MELI_CLIENT_SECRET")
MELI_SITE          = "MLA"        # Argentina
MELI_CURRENCY      = "ARS"

# Para título y descripción en MeLi
LISTING_TYPE       = "gold_special"  # free / bronze / silver / gold_special
CONDICION          = "new"
STOCK_INICIAL      = 3             # Unidades disponibles para empezar
TASA_FALLBACK      = 1200          # ARS/USD — sólo si no hay caché del dólar

OUTPUT_DIR       = os.path.dirname(os.path.abspath(__file__))
TOKEN_CACHE      = os.path.join(OUTPUT_DIR, ".meli_token.json")
DOLAR_CACHE      = os.path.join(OUTPUT_DIR, ".dolar_cache.json")
LOG_PUBLICACIONES = os.path.join(OUTPUT_DIR, "publicaciones_meli.csv")

MELI_ACCESS_TOKEN = ""
MELI_USER_ID      = ""


# ============================================================
# HELPERS
# ============================================================
def _headers():
    return {
        "Authorization": f"Bearer {MELI_ACCESS_TOKEN}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def _tasa_dolar():
    """Lee la tasa del caché del evaluador, o usa el fallback."""
    try:
        if os.path.exists(DOLAR_CACHE):
            with open(DOLAR_CACHE) as f:
                data = json.load(f)
            return float(data.get("tasa", TASA_FALLBACK))
    except Exception:
        pass
    return TASA_FALLBACK


# ============================================================
# TOKEN MERCADOLIBRE
# ============================================================
def obtener_token_meli():
    global MELI_ACCESS_TOKEN, MELI_USER_ID

    if not os.path.exists(TOKEN_CACHE):
        print("  ❌ No hay token de MeLi. Corré setup_meli_token.py primero.")
        return False

    try:
        with open(TOKEN_CACHE) as f:
            cache = json.load(f)

        expira = datetime.fromisoformat(cache["expira"])

        if datetime.now() < expira:
            MELI_ACCESS_TOKEN = cache["token"]
            MELI_USER_ID      = str(cache.get("user_id", ""))
            minutos = int((expira - datetime.now()).total_seconds() / 60)
            print(f"  🔑 Token válido — user_id: {MELI_USER_ID} | expira en {minutos} min")
            return True

        # Renovar con refresh_token
        refresh = cache.get("refresh_token", "")
        if not refresh:
            print("  ❌ Token expirado y sin refresh_token. Corré setup_meli_token.py.")
            return False

        print("  🔄 Renovando token...")
        r = requests.post(
            "https://api.mercadolibre.com/oauth/token",
            headers={"Accept": "application/json",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type":    "refresh_token",
                "client_id":     MELI_APP_ID,
                "client_secret": MELI_CLIENT_SECRET,
                "refresh_token": refresh,
            },
            timeout=15,
        )
        if r.status_code != 200:
            print(f"  ❌ Error renovando: {r.status_code} — {r.text[:100]}")
            return False

        data              = r.json()
        MELI_ACCESS_TOKEN = data["access_token"]
        MELI_USER_ID      = str(cache.get("user_id", ""))
        new_expira        = datetime.fromtimestamp(
            datetime.now().timestamp() + data.get("expires_in", 21600) - 300
        )
        cache.update({
            "token":         MELI_ACCESS_TOKEN,
            "refresh_token": data.get("refresh_token", refresh),
            "expira":        new_expira.isoformat(),
        })
        with open(TOKEN_CACHE, "w") as f:
            json.dump(cache, f, indent=2)

        print(f"  🔑 Token renovado (válido hasta {new_expira.strftime('%H:%M')})")
        return True

    except Exception as e:
        print(f"  ❌ Error con token: {e}")
        return False


# ============================================================
# LEER ÚLTIMO REPORTE
# ============================================================
def leer_ultimo_reporte():
    archivos = sorted(glob.glob(os.path.join(OUTPUT_DIR, "oportunidades_*.csv")))
    if not archivos:
        print("  ❌ No hay reportes CSV. Corré evaluador_productos.py primero.")
        return []

    ultimo = archivos[-1]
    print(f"  📊 {os.path.basename(ultimo)}")

    productos = []
    try:
        with open(ultimo, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if str(row.get("viable", "")).lower() in ("true", "1", "yes"):
                    productos.append(row)
    except Exception as e:
        print(f"  ❌ Error leyendo CSV: {e}")

    return productos


# ============================================================
# PRODUCTOS YA PUBLICADOS (evitar duplicados)
# ============================================================
def titulos_ya_publicados():
    publicados = set()
    if not os.path.exists(LOG_PUBLICACIONES):
        return publicados
    try:
        with open(LOG_PUBLICACIONES, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row.get("titulo", "").strip().lower()
                if t:
                    publicados.add(t)
    except Exception:
        pass
    return publicados


# ============================================================
# PREDICTOR DE CATEGORÍA MELI
# ============================================================
def predecir_categoria(nombre_producto):
    """
    Usa el endpoint de predicción de MeLi para encontrar la categoría.
    Retorna (category_id, domain_name) o ("", "") si falla.
    """
    try:
        r = requests.get(
            f"https://api.mercadolibre.com/sites/{MELI_SITE}/domain_discovery/search",
            params={"q": nombre_producto[:100], "limit": 3},
            headers=_headers(),
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            if data and isinstance(data, list):
                mejor = data[0]
                return mejor.get("category_id", ""), mejor.get("domain_name", "")
    except Exception:
        pass
    return "", ""


# ============================================================
# PUBLICAR EN MERCADOLIBRE
# ============================================================
def publicar_en_meli(titulo, categoria_id, precio_ars):
    """
    Crea la publicación en MeLi y añade la descripción.
    Retorna (ok: bool, mensaje: str, item_id: str, permalink: str)
    """
    # ── 1. Crear publicación ──────────────────────────────
    payload = {
        "title":              titulo[:60].strip(),
        "category_id":        categoria_id,
        "price":              int(precio_ars),
        "currency_id":        MELI_CURRENCY,
        "available_quantity": STOCK_INICIAL,
        "listing_type_id":    LISTING_TYPE,
        "condition":          CONDICION,
    }

    r = requests.post(
        "https://api.mercadolibre.com/items",
        headers=_headers(),
        json=payload,
        timeout=20,
    )

    if r.status_code not in (200, 201):
        # Si gold_special no está disponible para la cuenta, intentar con gold
        if r.status_code == 400 and "listing_type" in r.text.lower():
            payload["listing_type_id"] = "gold"
            r = requests.post(
                "https://api.mercadolibre.com/items",
                headers=_headers(),
                json=payload,
                timeout=20,
            )
        if r.status_code not in (200, 201):
            return False, f"Error {r.status_code}: {r.text[:250]}", "", ""

    data      = r.json()
    item_id   = data.get("id", "")
    permalink = data.get("permalink", "")

    # ── 2. Añadir descripción ─────────────────────────────
    descripcion = (
        "Producto importado directamente del fabricante, con garantía de calidad.\n\n"
        "✅ Nuevo en su empaque original\n"
        "📦 Envíos a todo el país\n"
        "💬 Consulte por combos, colores y modelos disponibles\n"
        "⭐ Respuesta inmediata — comprá con confianza"
    )

    try:
        requests.post(
            f"https://api.mercadolibre.com/items/{item_id}/descriptions",
            headers=_headers(),
            json={"plain_text": descripcion},
            timeout=10,
        )
    except Exception:
        pass  # La descripción es opcional; la publicación ya fue creada

    return True, "OK", item_id, permalink


# ============================================================
# LOG DE PUBLICACIONES
# ============================================================
def registrar_publicacion(titulo, item_id, permalink, categoria_id, precio_ars, multiplicador):
    existe = os.path.exists(LOG_PUBLICACIONES)
    with open(LOG_PUBLICACIONES, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if not existe:
            w.writerow(["fecha", "item_id", "permalink", "titulo",
                        "categoria_id", "precio_ars", "multiplicador"])
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            item_id, permalink, titulo[:80],
            categoria_id, int(precio_ars), multiplicador,
        ])


# ============================================================
# MAIN
# ============================================================
def main():
    print("\n🛒 PUBLICADOR AUTOMÁTICO — MERCADOLIBRE ARGENTINA")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # 0. Token
    print("0. Autenticando con MercadoLibre...")
    if not obtener_token_meli():
        input("\nPresioná Enter para cerrar...")
        return

    # 1. Cargar reporte
    print("\n1. Cargando reporte de productos viables...")
    productos = leer_ultimo_reporte()
    if not productos:
        print("   No hay productos viables. Corré evaluador_productos.py primero.")
        input("\nPresioná Enter para cerrar...")
        return
    print(f"   ✅ {len(productos)} productos viables")

    # 2. Filtrar ya publicados
    ya_publicados = titulos_ya_publicados()
    nuevos = [p for p in productos
              if p.get("nombre", "").strip().lower() not in ya_publicados]
    omitidos_dup = len(productos) - len(nuevos)
    if omitidos_dup:
        print(f"   ⚠ {omitidos_dup} ya publicados antes — se omiten")
    if not nuevos:
        print("   Todos los viables ya fueron publicados.")
        input("\nPresioná Enter para cerrar...")
        return

    tasa = _tasa_dolar()
    print(f"\n   Dólar blue caché: ARS {tasa}")

    publicados = 0
    omitidos   = 0
    errores    = 0

    print("\n" + "="*65)
    print("  COMANDOS: [s] publicar  [p] publicar con otro precio")
    print("            [n] siguiente  [q] salir")
    print("="*65)

    for i, p in enumerate(nuevos, 1):
        nombre    = p.get("nombre", "?")
        precio_ars_original = float(p.get("precio_prom_ars") or 0)
        precio_usd = float(p.get("precio_prom_usd") or 0)
        score      = p.get("score", "?")
        mult       = p.get("multiplicador", "?")
        costo_usd  = float(p.get("costo_total_usd") or 0)
        estimado   = str(p.get("precio_estimado", "")).lower() in ("true", "1")

        # Si el precio no está calculado, estimarlo ahora con la tasa actual
        if precio_ars_original <= 0 and costo_usd > 0:
            precio_ars_original = round(costo_usd * 4.0 * tasa)
            estimado = True
        elif precio_usd > 0 and precio_ars_original <= 0:
            precio_ars_original = round(precio_usd * tasa)

        print(f"\n[{i}/{len(nuevos)}] {nombre[:65]}")
        print(f"   Score: {score}/100 | Margen: {mult}x | Categoría TikTok: {p.get('categoria','N/A')[:40]}")
        print(f"   Precio TikTok USA: USD {p.get('precio_usd','?')} → "
              f"Costo importado: USD {p.get('costo_total_usd','?')}")
        tag = " (ESTIMADO — sin datos MeLi)" if estimado else " (precio MeLi real)"
        print(f"   Precio de venta sugerido: ARS {int(precio_ars_original):,}{tag}")
        print(f"   URL TikTok: {p.get('url','N/A')[:80]}")

        # Buscar categoría MeLi
        print(f"   Detectando categoría MeLi...", end=" ", flush=True)
        cat_id, cat_nombre = predecir_categoria(nombre)
        if cat_id:
            print(f"→ {cat_nombre} ({cat_id})")
        else:
            cat_id     = "MLA109027"  # Accesorios generales (fallback)
            cat_nombre = "Accesorios (fallback)"
            print(f"→ no detectada, usando {cat_nombre}")

        print(f"\n   ¿Qué hacemos? [s/p/n/q]: ", end="", flush=True)
        resp = input().strip().lower()

        if resp == "q":
            print("\n   Saliendo...")
            break

        if resp not in ("s", "p"):
            omitidos += 1
            continue

        precio_final = precio_ars_original
        if resp == "p":
            print(f"   Nuevo precio ARS (Enter para cancelar): ", end="", flush=True)
            raw = input().strip()
            if not raw:
                omitidos += 1
                continue
            try:
                precio_final = float(raw.replace(".", "").replace(",", ""))
            except ValueError:
                print("   Precio inválido, omitiendo.")
                omitidos += 1
                continue

        print(f"   Publicando en MeLi a ARS {int(precio_final):,}...", end=" ", flush=True)
        ok, msg, item_id, permalink = publicar_en_meli(nombre, cat_id, precio_final)

        if ok:
            print("✅")
            print(f"   ID: {item_id}")
            print(f"   URL: {permalink}")
            registrar_publicacion(nombre, item_id, permalink, cat_id, precio_final, mult)
            publicados += 1
        else:
            print("❌")
            print(f"   {msg}")
            errores += 1

        time.sleep(1)

    print(f"\n{'='*65}")
    print(f"✅ Publicados: {publicados} | Omitidos: {omitidos} | Errores: {errores}")
    if publicados > 0:
        print(f"   📊 Log guardado en: publicaciones_meli.csv")
    print()
    input("Presioná Enter para cerrar...")


if __name__ == "__main__":
    main()
