#!/usr/bin/env python3
"""
EVALUADOR AUTOMÁTICO DE PRODUCTOS PARA IMPORTACIÓN
Fuente: TikTok Shop via Apify (pratikdani/tiktok-shop-search-scraper) + MercadoLibre Argentina
Destino: Argentina via AliExpress/Alibaba, envío courier

Ejecutar en Windows:
    cd "C:\\Users\\storm\\Documents\\Claude\\Projects\\Importación"
    pip install requests
    python evaluador_productos.py

Token Apify: https://console.apify.com/account/integrations
Actor:        https://apify.com/pratikdani/tiktok-shop-search-scraper
"""

import requests
import json
import csv
import os
import re
import time
import webbrowser
import http.server
import urllib.parse
from datetime import datetime

# ============================================================
# CONFIGURACIÓN
# ============================================================
APIFY_TOKEN    = os.getenv("APIFY_TOKEN", "YOUR_APIFY_TOKEN")
APIFY_ACTOR_ID = "pratikdani~tiktok-shop-search-scraper"

# Credenciales MercadoLibre — el script obtiene el token automáticamente
MELI_APP_ID        = os.getenv("MELI_APP_ID", "YOUR_MELI_APP_ID")
MELI_CLIENT_SECRET = os.getenv("MELI_CLIENT_SECRET", "YOUR_MELI_CLIENT_SECRET")
MELI_REDIRECT_URI  = "https://httpbin.org/get"
MELI_TOKEN_CACHE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".meli_token.json")
MELI_ACCESS_TOKEN  = ""     # Se llena automáticamente al iniciar
MELI_BUSQUEDA_ACTIVA = False  # True cuando MeLi habilite el acceso a la búsqueda

# El actor requiere al menos una keyword para arrancar, pero devuelve el trending
# del país independientemente de la keyword. Usamos keywords de categorías distintas
# para forzar que el actor escanee diferentes verticales.
TIKTOK_KEYWORDS_POR_CATEGORIA = [
    # Belleza / skincare
    "gua sha", "lip oil", "scalp massager", "pore vacuum", "face ice roller",
    # Cocina
    "smash burger press", "rotary grater", "avocado slicer", "egg separator",
    # Hogar
    "cable management", "floating shelf", "lazy susan", "shoe rack organizer",
    # Fitness
    "ab wheel", "grip strengthener", "posture corrector", "resistance loop bands",
    # Mascotas
    "lick mat dog", "cat tunnel", "dog puzzle feeder",
    # Tech accesorios
    "phone ring holder", "webcam cover", "cable organizer box",
    # Auto
    "car seat organizer", "steering wheel tray",
    # Salud
    "nasal rinse", "neck traction device", "eye massager",
]
MAX_ITEMS_POR_KEYWORD = 10    # El actor devuelve máx 10 por llamada

# Amazon Movers & Shakers — productos que más subieron en ranking en las últimas 24h
# (NO Best Sellers = marcas establecidas; M&S = lo que está explotando AHORA)
AMAZON_CATEGORIAS = [
    ("Beauty",       "https://www.amazon.com/gp/movers-and-shakers/beauty/"),
    ("Kitchen",      "https://www.amazon.com/gp/movers-and-shakers/kitchen/"),
    ("Health",       "https://www.amazon.com/gp/movers-and-shakers/hpc/"),
    ("Sports",       "https://www.amazon.com/gp/movers-and-shakers/sporting-goods/"),
    ("Pets",         "https://www.amazon.com/gp/movers-and-shakers/pet-supplies/"),
    ("Home",         "https://www.amazon.com/gp/movers-and-shakers/garden/"),
    ("Tools",        "https://www.amazon.com/gp/movers-and-shakers/tools/"),
    ("Toys",         "https://www.amazon.com/gp/movers-and-shakers/toys-and-games/"),
    ("Baby",         "https://www.amazon.com/gp/movers-and-shakers/baby-products/"),
    ("Office",       "https://www.amazon.com/gp/movers-and-shakers/office-products/"),
    ("Electronics",  "https://www.amazon.com/gp/movers-and-shakers/electronics/"),
    ("Clothing",     "https://www.amazon.com/gp/movers-and-shakers/apparel/"),
]

# ────────────────────────────────────────────────────────────────
# CUENTAS DE INFLUENCERS — productos trending curados por humanos
# Formato: (nombre, url_beacons_o_linktree, categoria)
# Para agregar más cuentas: copiar una línea y editar.
# ────────────────────────────────────────────────────────────────
INFLUENCER_SOURCES = [
    ("OrganizationalHome", "https://beacons.ai/organizationalhome", "Home Organization"),
    # Agregá más acá:
    # ("NombreCuenta", "https://beacons.ai/cuenta",  "Categoría"),
    # ("NombreCuenta", "https://linktr.ee/cuenta",   "Categoría"),
]

# AliExpress — fuente China (precio REAL de importación + trending por categoría)
ALIEXPRESS_CATEGORIAS = [
    ("gadgets-hogar",  "home gadget organizer"),
    ("belleza",        "beauty skin care face"),
    ("fitness",        "fitness exercise band massage"),
    ("cocina",         "kitchen tool chopper"),
    ("mascotas",       "pet dog cat accessories"),
    ("tecnologia",     "phone stand wireless charger"),
    ("auto",           "car accessories organizer"),
    ("cabello",        "hair care growth tool"),
]

# Filtros de demanda
MIN_SALES_30D    = 100        # Mínimo 100 ventas en 30 días
MIN_RATIO_VENTA  = 0.05       # Mínimo ventas_30d / influencers
MAX_INFLUENCERS  = 100_000

# Filtros de precio
MIN_PRECIO_USD   = 5
MAX_PRECIO_USD   = 100

# Modelo de costos de importación Argentina
RATIO_ALIBABA        = 0.33   # Precio Alibaba ≈ 33% del precio TikTok Shop USA
FLETE_AEREO_USD      = 4.0    # Flete aéreo por unidad (lote 20-50 uds)
IVA_ARGENTINA        = 0.21   # IVA 21% en aduana (Decreto 1065/2024)
DERECHOS_ADUANA      = 0.05   # Derechos de importación ~5%
COMISION_MELI        = 0.15   # Comisión MercadoLibre 15%
MULTIPLICADOR_MINIMO = 2.5    # Mínimo rentable
TASA_USD_ARS         = 1200   # Se actualiza automáticamente cada semana

OUTPUT_DIR  = os.path.dirname(os.path.abspath(__file__))
DOLAR_CACHE = os.path.join(OUTPUT_DIR, ".dolar_cache.json")

# ============================================================
# ALERTAS REGULATORIAS — ARGENTINA
# Formato: keyword_lower → (nivel, descripción)
# Niveles: BLOQUEADO, COMPLEJO, MODERADO
# ============================================================
# ============================================================
# PALABRAS A EXCLUIR — productos no viables para importar a Argentina
# (médicos, movilidad, demasiado voluminosos, regulados como dispositivo médico)
# ============================================================
PALABRAS_EXCLUIR = [
    "wheelchair", "walker", "rollator", "cane", "crutch", "mobility scooter",
    "hospital bed", "stair lift", "hearing aid", "cpap", "nebulizer",
    "blood pressure monitor", "glucose monitor", "dialysis",
    "oxygen concentrator", "defibrillator", "pacemaker",
    "funeral", "coffin", "casket",
    "gun", "firearm", "ammo", "ammunition", "rifle", "pistol",
    "car seat" ,  # bulky, high IRAM cert
]

ALERTAS_REGULATORIAS = {
    # ── BLOQUEADO: no importar sin asesoría legal especializada ──────────
    "protein powder":    ("BLOQUEADO 🚫", "ANMAT+SENASA: alimento-suplemento, registro larguísimo"),
    "whey protein":      ("BLOQUEADO 🚫", "ANMAT+SENASA: alimento-suplemento"),
    "creatine":          ("BLOQUEADO 🚫", "ANMAT+SENASA: suplemento deportivo"),
    "pre-workout":       ("BLOQUEADO 🚫", "ANMAT+SENASA: suplemento deportivo"),
    "pre workout":       ("BLOQUEADO 🚫", "ANMAT+SENASA: suplemento deportivo"),
    "energy drink":      ("BLOQUEADO 🚫", "SENASA: bebida energética, habilitación compleja"),
    "drink mix":         ("BLOQUEADO 🚫", "SENASA: alimento procesado, habilitación compleja"),
    "fat burner":        ("BLOQUEADO 🚫", "ANMAT: producto para adelgazar, restricción estricta"),
    "weight loss":       ("BLOQUEADO 🚫", "ANMAT: producto para adelgazar, restricción estricta"),

    # ── COMPLEJO: posible pero requiere gestión regulatoria seria ─────────
    "supplement":        ("COMPLEJO ⚠️", "ANMAT: suplemento dietario requiere RNPA (meses de trámite)"),
    "vitamin":           ("COMPLEJO ⚠️", "ANMAT: vitaminas requieren registro sanitario"),
    "magnesium":         ("COMPLEJO ⚠️", "ANMAT: mineral-suplemento requiere RNPA"),
    "collagen supplement":("COMPLEJO ⚠️","ANMAT: suplemento de colágeno requiere RNPA"),
    "melatonin":         ("COMPLEJO ⚠️", "ANMAT: considerado medicamento en Argentina"),
    "wireless charger":  ("COMPLEJO ⚠️", "ENACOM: electrónico inalámbrico requiere certificación"),
    "bluetooth":         ("COMPLEJO ⚠️", "ENACOM: dispositivo bluetooth requiere certificación"),
    "electric shaver":   ("COMPLEJO ⚠️", "ENACOM + seguridad eléctrica"),
    "hair dryer":        ("COMPLEJO ⚠️", "ENACOM + seguridad eléctrica"),
    "laser":             ("COMPLEJO ⚠️", "ANMAT: dispositivo láser requiere registro"),

    # ── MODERADO: posible, hay un trámite pero no es prohibitivo ─────────
    "serum":             ("MODERADO ℹ️", "ANMAT: cosmético requiere RNPA cosmético (gestionable)"),
    "retinol":           ("MODERADO ℹ️", "ANMAT: cosmético con activo requiere RNPA"),
    "sunscreen":         ("MODERADO ℹ️", "ANMAT: FPS requiere RNPA especial de cosméticos"),
    "whitening strip":   ("MODERADO ℹ️", "ANMAT: blanqueador dental puede requerir registro"),
    "teeth whitening":   ("MODERADO ℹ️", "ANMAT: blanqueador dental puede requerir registro"),
    "face cream":        ("MODERADO ℹ️", "ANMAT: cosmético requiere RNPA (proceso gestionable)"),
    "moisturizer":       ("MODERADO ℹ️", "ANMAT: cosmético requiere RNPA"),
    "toy":               ("MODERADO ℹ️", "IRAM: juguetes requieren certificación de seguridad"),
}

# Variable global: trending de MeLi Argentina (se llena en main)
MELI_TRENDING = []


# ============================================================
# MERCADOLIBRE — OAUTH AUTOMÁTICO (sin intervención manual)
# ============================================================
def _oauth_flow_meli():
    """
    Abre Playwright en modo VISIBLE para que el usuario haga login.
    Captura el código automáticamente cuando MeLi redirige a httpbin.
    Sin copy-paste, sin expiración por demora.
    """
    auth_url = (
        "https://auth.mercadolibre.com.ar/authorization"
        "?response_type=code"
        f"&client_id={MELI_APP_ID}"
        f"&redirect_uri={urllib.parse.quote(MELI_REDIRECT_URI, safe='')}"
    )

    print()
    print("  ┌──────────────────────────────────────────────────────────┐")
    print("  │  AUTENTICACIÓN MERCADOLIBRE (solo esta vez)              │")
    print("  │                                                          │")
    print("  │  Se abre un browser. Iniciá sesión y hacé click en      │")
    print("  │  'Permitir acceso'. El código se captura automáticamente.│")
    print("  └──────────────────────────────────────────────────────────┘")
    print()

    # Abrir Chrome (Sebastian usa Chrome, siempre abrir Chrome explícitamente)
    import subprocess
    _chrome_paths = [
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    _chrome = next((p for p in _chrome_paths if os.path.exists(p)), None)
    if _chrome:
        subprocess.Popen([_chrome, auth_url])
    else:
        webbrowser.open(auth_url)

    print("  ⏳ Esperando que autorices en Chrome...")
    print("     Cuando llegues a httpbin.org, copiá la URL del address bar y pegala acá.")
    print()
    raw = input("  URL de httpbin: ").strip()
    if not raw:
        return None

    # Extraer código: acepta URL completa, URL parcial, o código directo
    code = None
    if "httpbin.org" in raw or "code=" in raw:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
        code = qs.get("code", [None])[0]
        if not code:
            m = re.search(r'code=([^&\s"]+)', raw)
            if m:
                code = m.group(1)
    if not code:
        # Asumir que pegaron el código directamente
        code = raw.strip().strip('"\'')

    if not code or len(code) < 10:
        print(f"  ❌ Código inválido: '{raw[:50]}'")
        return None
    print(f"  ✅ Código capturado. Obteniendo token...")

    if not code:
        print("  ❌ No se pudo capturar el código.")
        return None

    print(f"  ✅ Código capturado. Obteniendo token...")
    for intento in range(3):
        r = requests.post(
            "https://api.mercadolibre.com/oauth/token",
            headers={"Accept": "application/json",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type":   "authorization_code",
                "client_id":    MELI_APP_ID,
                "client_secret":MELI_CLIENT_SECRET,
                "code":         code,
                "redirect_uri": MELI_REDIRECT_URI,
            },
            timeout=15,
        )
        if r.status_code == 429:
            espera = 10 * (intento + 1)
            print(f"  ⏳ Rate limit MeLi — esperando {espera}s...")
            time.sleep(espera)
            continue
        break
    if r.status_code != 200:
        print(f"  ❌ Error: {r.status_code} — {r.text[:200]}")
        return None

    data    = r.json()
    token   = data.get("access_token", "")
    ref     = data.get("refresh_token", "")
    exp     = data.get("expires_in", 21600)
    user_id = data.get("user_id", "")
    expira  = datetime.fromtimestamp(datetime.now().timestamp() + exp - 300).isoformat()

    import json as _j
    with open(MELI_TOKEN_CACHE, "w") as f:
        _j.dump({
            "token": token, "refresh_token": ref,
            "expira": expira, "user_id": str(user_id), "tipo": "authorization_code",
        }, f, indent=2)

    print(f"  ✅ Token guardado. Próximas ejecuciones serán 100% automáticas.")
    return token


# ============================================================
# MERCADOLIBRE — TOKEN AUTOMÁTICO
# ============================================================
def obtener_token_meli():
    global MELI_ACCESS_TOKEN
    import json as _json

    if not os.path.exists(MELI_TOKEN_CACHE):
        print("  ⚠ Sin token MeLi — iniciando autenticación automática...")
        return _oauth_flow_meli() or ""

    try:
        with open(MELI_TOKEN_CACHE, "r") as f:
            cache = _json.load(f)

        expira = datetime.fromisoformat(cache["expira"])

        if datetime.now() < expira:
            MELI_ACCESS_TOKEN = cache["token"]
            minutos = int((expira - datetime.now()).total_seconds() / 60)
            tipo = cache.get("tipo", "desconocido")
            user = cache.get("user_id", "?")
            print(f"  🔑 Token MeLi válido — tipo: {tipo} | user_id: {user} | expira en {minutos} min")
            return MELI_ACCESS_TOKEN

        refresh_token = cache.get("refresh_token", "")
        if not refresh_token:
            print("  ⚠ Token MeLi expirado sin refresh_token — re-autenticando automáticamente...")
            return _oauth_flow_meli() or ""

        print("  🔄 Token MeLi expirado — renovando...")
        r = requests.post(
            "https://api.mercadolibre.com/oauth/token",
            headers={"Accept": "application/json",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type":    "refresh_token",
                "client_id":     MELI_APP_ID,
                "client_secret": MELI_CLIENT_SECRET,
                "refresh_token": refresh_token,
            },
            timeout=15,
        )
        if r.status_code != 200:
            print(f"  ⚠ Error renovando token: {r.status_code} — {r.text[:100]}")
            return ""

        data      = r.json()
        token     = data.get("access_token", "")
        new_ref   = data.get("refresh_token", refresh_token)
        expires   = data.get("expires_in", 21600)
        expira_en = datetime.fromtimestamp(datetime.now().timestamp() + expires - 300)

        cache.update({"token": token, "refresh_token": new_ref,
                      "expira": expira_en.isoformat()})
        with open(MELI_TOKEN_CACHE, "w") as f:
            _json.dump(cache, f, indent=2)

        MELI_ACCESS_TOKEN = token
        print(f"  🔑 Token MeLi renovado (válido por {expires//3600}h)")
        return token

    except Exception as e:
        print(f"  ⚠ Error con token MeLi: {e}")
        return ""


# ============================================================
# TIPO DE CAMBIO — DÓLAR BLUE (actualización semanal)
# ============================================================
def obtener_tasa_dolar():
    import json as _json
    FUENTES = [
        {"url": "https://dolarhoy.com/i/tasas-y-tipos-de-cambio/dolar-blue",
         "parser": "_parse_dolarhoy"},
        {"url": "https://api.dolarito.ar/api/informal",
         "parser": "_parse_dolarito"},
        {"url": "https://api.argentinadatos.com/v1/cotizaciones/dolares/blue",
         "parser": "_parse_argentinadatos"},
    ]

    if os.path.exists(DOLAR_CACHE):
        try:
            with open(DOLAR_CACHE, "r") as f:
                cache = _json.load(f)
            dias = (datetime.now() - datetime.fromisoformat(cache["fecha"])).days
            if dias < 1:
                print(f"  💵 Dólar blue: ARS {cache['tasa']} (caché de hoy)")
                return cache["tasa"]
        except Exception:
            pass

    tasa = None
    for fuente in FUENTES:
        try:
            r = requests.get(fuente["url"], timeout=8,
                             headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            if fuente["parser"] == "_parse_dolarhoy":
                texto = r.text
                m = re.search(r'blue.*?(\d[\d\.,]+)', texto, re.IGNORECASE | re.DOTALL)
                if m:
                    tasa = float(m.group(1).replace(".", "").replace(",", "."))
            elif fuente["parser"] == "_parse_dolarito":
                data = r.json()
                tasa = float(data.get("venta", 0))
            elif fuente["parser"] == "_parse_argentinadatos":
                data = r.json()
                if isinstance(data, list) and data:
                    tasa = float(data[-1].get("venta", 0))
                elif isinstance(data, dict):
                    tasa = float(data.get("venta", 0))
            if tasa and tasa > 100:
                break
        except Exception:
            continue

    if tasa and tasa > 100:
        try:
            with open(DOLAR_CACHE, "w") as f:
                _json.dump({"tasa": tasa, "fecha": datetime.now().isoformat()}, f)
        except Exception:
            pass
        print(f"  💵 Dólar blue actualizado: ARS {tasa}")
        return tasa
    else:
        print(f"  ⚠ No se pudo obtener el dólar blue — usando valor por defecto: {TASA_USD_ARS}")
        return TASA_USD_ARS


# ============================================================
# TRENDING MERCADOLIBRE ARGENTINA (fuente adicional, gratis)
# ============================================================
def obtener_trending_meli():
    """
    Obtiene las búsquedas trending en MeLi Argentina.
    Endpoint público: GET /trends/MLA (no requiere auth).
    Retorna lista de keywords en minúsculas.
    """
    global MELI_TRENDING
    try:
        headers = {}
        if MELI_ACCESS_TOKEN:
            headers["Authorization"] = f"Bearer {MELI_ACCESS_TOKEN}"
        r = requests.get(
            "https://api.mercadolibre.com/trends/MLA",
            headers=headers, timeout=10,
        )
        if r.status_code == 401 and headers:
            r = requests.get("https://api.mercadolibre.com/trends/MLA", timeout=10)
        if r.status_code == 429:
            time.sleep(5)
            r = requests.get("https://api.mercadolibre.com/trends/MLA", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                MELI_TRENDING = [item.get("keyword", "").lower() for item in data]
                print(f"  📈 MeLi Trending: {len(MELI_TRENDING)} búsquedas obtenidas")
                if MELI_TRENDING[:5]:
                    print(f"     Top 5: {', '.join(MELI_TRENDING[:5])}")
                return MELI_TRENDING
        print(f"  ⚠ MeLi Trending no disponible (HTTP {r.status_code})")
    except Exception as e:
        print(f"  ⚠ MeLi Trending: {e}")
    MELI_TRENDING = []
    return []


def get_meli_trending_productos(tasa_usd):
    """
    Scrapea listado.mercadolibre.com.ar para cada keyword trending.
    No usa la API (403 para apps nuevas), usa scraping directo HTML.
    Retorna hasta 100 productos con precio en ARS convertido a USD.
    """
    if not MELI_TRENDING or not tasa_usd:
        return []

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "es-AR,es;q=0.9",
        "Accept": "text/html,*/*",
    }
    try:
        from bs4 import BeautifulSoup as _BS
    except ImportError:
        print("  ⚠ Instalar beautifulsoup4")
        return []

    todos  = []
    vistos = set()
    MAX_KW  = 20
    POR_KW  = 5

    _debug_guardado = False

    def _parsear_meli_html(html, kw):
        """Parsea HTML de MeLi y retorna lista de (titulo, precio_ars, url)."""
        soup = _BS(html, "html.parser")
        # Probar varios selectores (MeLi puede cambiar nombres de clase)
        CARD_SELS = [
            ".ui-search-layout__item",
            ".ui-search-result",
            "[class*='search-result']",
            "[class*='search-layout__item']",
        ]
        TITLE_SELS = [
            ".ui-search-item__title",
            "h2.ui-search-item__title",
            "[class*='item__title']",
            "h2", "h3",
        ]
        PRICE_SELS = [
            ".andes-money-amount__fraction",
            "[class*='price__fraction']",
            "[class*='money-amount__fraction']",
            "[class*='price'] .fraction",
        ]
        cards = []
        for sel in CARD_SELS:
            cards = soup.select(sel)
            if cards:
                break

        resultados = []
        for card in cards[:POR_KW]:
            t_el = None
            for sel in TITLE_SELS:
                t_el = card.select_one(sel)
                if t_el:
                    break
            if not t_el:
                continue
            titulo = t_el.get_text(strip=True)
            if not titulo or len(titulo) < 5:
                continue

            p_el = None
            for sel in PRICE_SELS:
                p_el = card.select_one(sel)
                if p_el:
                    break

            precio_ars = 0.0
            if p_el:
                # MeLi usa "." como separador de miles en ARS (ej: "50.990")
                precio_ars = parse_precio(p_el.get_text(strip=True).replace(".", "").replace(",", ""))

            a = card.select_one("a[href*='mercadolibre']")
            prod_url = a.get("href", "").split("?")[0] if a else ""
            resultados.append((titulo, precio_ars, prod_url))

        # Debug: si no hay cards, guardar HTML una sola vez
        nonlocal _debug_guardado
        if not cards and not _debug_guardado:
            _debug_guardado = True
            _dp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_meli_debug.html")
            with open(_dp, "w", encoding="utf-8") as _f:
                _f.write(html)
            all_cls = set()
            for tag in soup.find_all(True, limit=200):
                for c in tag.get("class", []):
                    all_cls.add(c)
            cls_rel = [c for c in sorted(all_cls) if any(x in c for x in ["search", "result", "item", "price", "layout"])]
            print(f"\n    ⚠ MeLi: 0 cards. Clases: {cls_rel[:12]}")
            print(f"    → HTML guardado en _meli_debug.html")
        return resultados

    for kw in MELI_TRENDING[:MAX_KW]:
        kw_url = kw.strip().replace(" ", "-")
        url    = f"https://listado.mercadolibre.com.ar/{urllib.parse.quote(kw_url)}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
            html = r.text if r.status_code == 200 else None

            # Fallback Playwright si requests no trae resultados
            if not html or len(html) < 5000:
                html = _playwright_get_html(url, wait_ms=3000) or ""

            for titulo, precio_ars, prod_url in _parsear_meli_html(html, kw):
                pid = titulo[:40].lower()
                if pid in vistos:
                    continue
                vistos.add(pid)
                precio_usd = round(precio_ars / tasa_usd, 2) if precio_ars else 0.0
                todos.append({
                    "product_title":      titulo,
                    "min_price":          f"${precio_usd:.2f}" if precio_usd else "0",
                    "_tiene_precio_real": precio_usd > 0,
                    "_precio_real_usd":   precio_usd if precio_usd else None,
                    "_precio_ars":        precio_ars,
                    "total_sale_30d_cnt": 500,
                    "total_sale_7d_cnt":  100,
                    "influencers_count":  0,
                    "product_rating":     "4.0",
                    "review_count":       "100",
                    "category":           kw,
                    "_fuente":            "MeLi/Trending",
                    "_meli_local":        True,
                    "product_url":        prod_url,
                    "_trending_keyword":  kw,
                })
        except Exception:
            pass
        time.sleep(0.3)

    return todos


# ============================================================
# RESTRICCIONES REGULATORIAS
# ============================================================
def check_restricciones(nombre, categoria=""):
    """
    Verifica si el producto tiene restricciones de importación/venta en Argentina.
    Retorna (nivel, descripcion). Si no hay restricción: ("OK ✅", "Sin restricciones conocidas").
    """
    texto = (nombre + " " + str(categoria)).lower()

    # Orden de severidad: primero los más graves
    orden = ["BLOQUEADO 🚫", "COMPLEJO ⚠️", "MODERADO ℹ️"]
    encontrados = {}

    for keyword, (nivel, desc) in ALERTAS_REGULATORIAS.items():
        if keyword in texto:
            if nivel not in encontrados:
                encontrados[nivel] = desc

    # Devolver el más severo
    for nivel in orden:
        if nivel in encontrados:
            return nivel, encontrados[nivel]

    return "OK ✅", "Sin restricciones conocidas"


def _match_trending(nombre, categoria=""):
    """
    Verifica si el producto hace match con alguna búsqueda trending de MeLi.
    Usa la traducción española del nombre para mayor precisión.
    """
    if not MELI_TRENDING:
        return False, ""

    # Traducir a español para comparar con el trending (que está en español)
    query_es = query_para_meli(nombre, categoria).lower()
    nombre_lower = nombre.lower()

    for trend in MELI_TRENDING:
        trend_words = trend.split()
        # Match si 2+ palabras del trending aparecen en la query española
        if len(trend_words) >= 2:
            matches = sum(1 for w in trend_words if w in query_es or w in nombre_lower)
            if matches >= 2:
                return True, trend
        elif len(trend_words) == 1:
            if trend_words[0] in query_es:
                return True, trend

    return False, ""


# ============================================================
# EXTRACTOR DE PRECIOS — Amazon / AliExpress desde links externos
# ============================================================
_AMAZON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

def _extraer_precio_amazon(url):
    """
    Intenta extraer el precio en USD de una página de producto Amazon.
    Retorna float o 0.0 si no encuentra.
    """
    if not url or "amazon." not in url:
        return 0.0
    # Las páginas de búsqueda (/s?k=) no tienen precio directo del producto
    if "/s?" in url and ("k=" in url or "search=" in url):
        return 0.0
    try:
        r = requests.get(url, headers=_AMAZON_HEADERS, timeout=12, allow_redirects=True)
        if r.status_code == 200:
            html = r.text
            # Detectar moneda: USD ($), EUR (€), GBP (£)
            es_eur = "amazon.de" in r.url or "amazon.fr" in r.url or "amazon.it" in r.url or "amazon.es" in r.url
            es_gbp = "amazon.co.uk" in r.url
            # Patrones USD
            patrones_usd = [
                r'"priceAmount"\s*:\s*([\d.]+)',
                r'class="a-offscreen">\$([\d,]+\.?\d*)<',
                r'id="priceblock_ourprice"[^>]*>\s*\$([\d,]+\.?\d*)',
                r'id="priceblock_dealprice"[^>]*>\s*\$([\d,]+\.?\d*)',
                r'"price"\s*:\s*"?\$([\d,]+\.?\d*)"?',
            ]
            # Patrones multi-moneda
            patrones_eur = [
                r'class="a-offscreen">€\s*([\d,.]+)<',
                r'"priceAmount"\s*:\s*([\d.]+)',
            ]
            patrones_gbp = [
                r'class="a-offscreen">£\s*([\d,.]+)<',
                r'"priceAmount"\s*:\s*([\d.]+)',
            ]
            patrones = patrones_eur if es_eur else (patrones_gbp if es_gbp else patrones_usd)
            factor   = 1.1 if es_eur else (1.27 if es_gbp else 1.0)   # conv aprox a USD
            for pat in patrones:
                m = re.search(pat, html, re.DOTALL)
                if m:
                    precio = parse_precio(m.group(1).replace(",", ""))
                    if 1.0 < precio < 2000.0:
                        return round(precio * factor, 2)
    except Exception:
        pass
    return 0.0

def _extraer_links_amazon(html_contenido):
    """Extrae URLs de Amazon directas de un bloque HTML."""
    return re.findall(
        r'href=["\']?(https?://(?:www\.)?amazon\.(?:com|de|co\.uk|fr|it|es|ca)/[^\s"\'<>]{10,300})["\']?',
        html_contenido
    )

def _extraer_links_afiliados(html_contenido):
    """Extrae links de afiliados que pueden redirigir a Amazon."""
    return re.findall(
        r'href=["\']?(https?://(?:rstyle\.me|go\.magik\.ly|amzn\.to|clk\.tradedoubler|awin1\.com|click\.linksynergy|imp\.i305022|bit\.ly)[^\s"\'<>]{5,250})["\']?',
        html_contenido
    )

def _seguir_redirect(url, timeout=8):
    """Sigue redirects y retorna la URL final. Para links de afiliados."""
    _h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout, headers=_h)
        return r.url
    except Exception:
        try:
            r = requests.get(url, allow_redirects=True, timeout=timeout, stream=True, headers=_h)
            r.close()
            return r.url
        except Exception:
            return url


# ============================================================
# PLAYWRIGHT — browser headless para sitios con Cloudflare/JS
# ============================================================
def _playwright_get_html(url, wait_ms=2500, pre_cookies=None):
    """
    Renderiza una URL con Chromium headless real.
    pre_cookies: lista de dicts con {name, value, domain, path} a setear antes de navegar.
    Retorna HTML (str) o None si playwright no está instalado o falla.
    Instalar: pip install playwright && playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                viewport={"width": 1280, "height": 800},
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            if pre_cookies:
                ctx.add_cookies(pre_cookies)
            page = ctx.new_page()
            # Ocultar webdriver flag (anti-bot)
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(wait_ms)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        print(f"[Playwright] {e}")
        return None


# ============================================================
# PARSERS DE DATOS
# ============================================================
def parse_precio(val):
    if val is None:
        return 0.0
    s = str(val).replace("$", "").replace(",", "").strip()
    try:
        if s.upper().endswith("K"):
            return float(s[:-1]) * 1_000
        if s.upper().endswith("M"):
            return float(s[:-1]) * 1_000_000
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def parse_num(val):
    if val is None:
        return 0
    s = str(val).replace(",", "").strip()
    try:
        if s.upper().endswith("K"):
            return int(float(s[:-1]) * 1_000)
        if s.upper().endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _campo(obj, nombres, default=None):
    for n in nombres:
        if n in obj and obj[n] is not None and obj[n] != "":
            return obj[n]
    return default


# ============================================================
# TIKTOK SHOP — Creative Center API (sin Apify, sin costo)
# ============================================================
_TIKTOK_CC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer":        "https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en",
    "Accept":         "application/json, text/plain, */*",
    "Accept-Language":"en-US,en;q=0.9",
    "Origin":         "https://ads.tiktok.com",
}

# Categorías del Creative Center (id, nombre)
_TIKTOK_CC_CATS = [
    ("",       "All"),           # sin filtro → trending global
    ("13",     "Beauty"),
    ("15",     "Home & Kitchen"),
    ("9",      "Sports & Outdoors"),
    ("5",      "Pet Supplies"),
    ("6",      "Toys & Games"),
]


def _tiktok_cc_fetch(cat_id, periodo=7):
    """
    Scrapea TikTok Shop US trending con Playwright.
    Prueba la página pública de trending items de TikTok Shop.
    """
    urls_a_probar = [
        "https://shop.tiktok.com/us/k/tiktok-trending-items",
        "https://www.tiktok.com/shop/us/trending",
        "https://ads.tiktok.com/business/creativecenter/top-products/pc/en",
    ]
    for url in urls_a_probar:
        html = _playwright_get_html(url, wait_ms=5000)
        if not html:
            continue
        try:
            from bs4 import BeautifulSoup as _BS
            soup = _BS(html, "html.parser")
            items = []

            # Buscar JSON embebido (Next.js / React)
            for script in soup.find_all("script"):
                txt = script.string or ""
                for key in ("product_name", "productName", "goods_name", "item_title"):
                    if key in txt:
                        for m in re.finditer(r'"' + key + r'"\s*:\s*"([^"]{5,100})"', txt):
                            items.append({"product_name": m.group(1)})
                if items:
                    break

            # Fallback: cards del HTML renderizado
            if not items:
                selectors = [
                    "[class*='product-title']", "[class*='ProductTitle']",
                    "[class*='item-title']", "[class*='goods-name']",
                    "h3", "[data-e2e*='product']",
                ]
                for sel in selectors:
                    for el in soup.select(sel)[:30]:
                        txt = el.get_text(strip=True)
                        if len(txt) > 8:
                            items.append({"product_name": txt})
                    if items:
                        break

            if items:
                return items[:50], None
        except Exception as e:
            continue
    return [], None


def _walmart_trending():
    """Fallback: scraping de Walmart Trending Products."""
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    productos = []
    try:
        r = requests.get(
            "https://www.walmart.com/shop/trending-products",
            headers=HEADERS, timeout=20, allow_redirects=True,
        )
        if r.status_code != 200:
            return productos
        # Walmart embeds JSON en __NEXT_DATA__
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(\{.+?\})</script>', r.text, re.DOTALL)
        if not m:
            return productos
        nd = json.loads(m.group(1))
        # Navegar hasta los items
        items = []
        def _dig(obj, depth=0):
            if depth > 10 or not isinstance(obj, dict):
                return
            if "name" in obj and "priceInfo" in obj:
                items.append(obj)
                return
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    if isinstance(v, list):
                        for el in v:
                            _dig(el, depth+1)
                    else:
                        _dig(v, depth+1)
        _dig(nd)
        for item in items:
            titulo = item.get("name", "")
            if not titulo:
                continue
            precio = 0.0
            pi = item.get("priceInfo", {})
            if isinstance(pi, dict):
                precio = float(pi.get("currentPrice", pi.get("price", 0)) or 0)
            productos.append({
                "product_title":       titulo,
                "min_price":           f"${precio:.2f}" if precio else "$25",
                "total_sale_30d_cnt":  300,
                "total_sale_7d_cnt":   60,
                "influencers_count":   10,
                "product_rating":      str(item.get("averageRating", 0)),
                "review_count":        str(item.get("numberOfReviews", 0)),
                "_fuente":             "Walmart/US",
            })
    except Exception:
        pass
    return productos


def get_tiktok_products():
    """
    Obtiene productos trending desde TikTok Creative Center (sin Apify).
    Fallback a Walmart Trending si CC no responde.
    """
    vistos, todos = set(), []

    print(f"  Probando TikTok Creative Center ({len(_TIKTOK_CC_CATS)} categorías)...")
    cc_ok = False
    for cat_id, cat_nombre in _TIKTOK_CC_CATS:
        print(f"    [{cat_nombre}]...", end=" ", flush=True)
        items, err = _tiktok_cc_fetch(cat_id)
        if err or items is None:
            print(f"⚠ {err}")
            continue
        nuevos = 0
        for p in items:
            pid = str(p.get("product_id", p.get("id", ""))) or str(p.get("product_name", ""))[:40]
            if not pid or pid in vistos:
                continue
            vistos.add(pid)
            titulo = p.get("product_name", p.get("title", p.get("name", "")))
            if not titulo:
                continue
            precio = 0.0
            for campo in ("min_price", "price", "sale_price"):
                v = p.get(campo)
                if v:
                    precio = parse_precio(str(v))
                    break
            todos.append({
                "product_title":      titulo,
                "min_price":          f"${precio:.2f}" if precio else "$20",
                "total_sale_30d_cnt": parse_num(str(p.get("sold_count", p.get("sales_count", 500)))),
                "total_sale_7d_cnt":  parse_num(str(p.get("sold_count_7d", 100))),
                "influencers_count":  parse_num(str(p.get("creator_count", p.get("influencer_count", 10)))),
                "product_rating":     str(p.get("product_rating", p.get("rating", 0))),
                "review_count":       str(p.get("review_count", p.get("review_cnt", 0))),
                "category":           cat_nombre,
                "_fuente":            "TikTok/CC",
            })
            nuevos += 1
        print(f"{nuevos} productos")
        if nuevos > 0:
            cc_ok = True
        time.sleep(0.3)

    if not cc_ok:
        print("  ⚠ TikTok CC sin datos — usando Walmart Trending como reemplazo...")
        wm = _walmart_trending()
        for p in wm:
            pid = p["product_title"][:40].lower()
            if pid not in vistos:
                vistos.add(pid)
                todos.append(p)
        print(f"  Walmart: {len(wm)} productos")

    # ── Temu Bestsellers via Playwright (productos chinos en EEUU = señal directa) ──
    print("  Temu Bestsellers (Playwright)...", end=" ", flush=True)
    html_temu = _playwright_get_html("https://www.temu.com/channel/best-seller.html", wait_ms=4000)
    temu_nuevos = 0
    if html_temu:
        try:
            from bs4 import BeautifulSoup as _BS4T
            soup_t = _BS4T(html_temu, "html.parser")
            # Temu embeds JSON en <script id="__NEXT_DATA__"> o scripts con window.__DATA__
            nd_tag = soup_t.find("script", {"id": "__NEXT_DATA__"})
            if nd_tag:
                nd = json.loads(nd_tag.string or "{}")
                # Extraer items recursivamente
                items_temu = []
                def _dig_temu(obj, depth=0):
                    if depth > 12 or not isinstance(obj, dict):
                        return
                    # Temu usa "goods_name" o "name" + "price"
                    if ("goods_name" in obj or ("name" in obj and "price" in obj)):
                        items_temu.append(obj)
                        return
                    for v in obj.values():
                        if isinstance(v, list):
                            for el in v:
                                _dig_temu(el, depth + 1)
                        elif isinstance(v, dict):
                            _dig_temu(v, depth + 1)
                _dig_temu(nd)
                for item in items_temu:
                    titulo = item.get("goods_name", item.get("name", item.get("title", "")))
                    if not titulo:
                        continue
                    pid = titulo[:40].lower()
                    if pid in vistos:
                        continue
                    vistos.add(pid)
                    precio_raw = item.get("price", item.get("sale_price", item.get("min_price", 0)))
                    precio = parse_precio(str(precio_raw))
                    todos.append({
                        "product_title":      titulo,
                        "min_price":          f"${precio:.2f}" if precio else "$15",
                        "total_sale_30d_cnt": parse_num(str(item.get("sold_count", item.get("sales", 200)))),
                        "total_sale_7d_cnt":  40,
                        "influencers_count":  5,
                        "product_rating":     str(item.get("rating", item.get("score", 0))),
                        "review_count":       str(item.get("review_count", item.get("comment_num", 0))),
                        "_fuente":            "Temu/US",
                    })
                    temu_nuevos += 1
            else:
                # Fallback: extraer product cards del HTML
                for card in soup_t.select("[class*='goods-item'], [class*='product-card'], [data-type='goods']"):
                    t_el = card.select_one("[class*='goods-name'], [class*='name'], [class*='title']")
                    p_el = card.select_one("[class*='price']")
                    if not t_el:
                        continue
                    titulo = t_el.get_text(strip=True)
                    pid = titulo[:40].lower()
                    if not titulo or len(titulo) < 5 or pid in vistos:
                        continue
                    vistos.add(pid)
                    precio = parse_precio(p_el.get_text(strip=True) if p_el else "0")
                    todos.append({
                        "product_title":      titulo,
                        "min_price":          f"${precio:.2f}" if precio else "$15",
                        "total_sale_30d_cnt": 200,
                        "total_sale_7d_cnt":  40,
                        "influencers_count":  5,
                        "product_rating":     "4.0",
                        "review_count":       "0",
                        "_fuente":            "Temu/US",
                    })
                    temu_nuevos += 1
        except Exception as e:
            print(f"⚠ parse error: {e}")
    else:
        print("(Playwright no disponible — corré Setup Playwright.bat)")
    print(f"{temu_nuevos} productos de Temu")

    print(f"  Total TikTok/trending: {len(todos)} productos")
    return todos


# ============================================================
# AMAZON BEST SELLERS — segunda fuente
# ============================================================
def get_amazon_movers():
    """
    Scraping de Amazon Best Sellers (6 categorías, top 30 por categoría).
    Usa html.parser estándar. Si Amazon bloquea, retorna lista vacía sin romper el script.
    Los productos de Amazon se identifican por su título y precio estimado.
    """
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }

    # Intentar usar BeautifulSoup si está disponible
    try:
        from bs4 import BeautifulSoup
        _tiene_bs4 = True
    except ImportError:
        _tiene_bs4 = False

    todos   = []
    vistos  = set()

    for cat_nombre, url in AMAZON_CATEGORIAS:
        print(f"  📈 Amazon M&S {cat_nombre}...", end=" ", flush=True)
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                print(f"HTTP {r.status_code} (bloqueado o lento)")
                time.sleep(2)
                continue

            html_text = r.text
            productos_cat = []

            if _tiene_bs4:
                # Parser robusto con BeautifulSoup
                soup = BeautifulSoup(html_text, "html.parser")
                items = soup.select("div.zg-item-immersion, li.zg-item, div[id^='gridItemRoot']")
                for item in items[:30]:
                    titulo_el = item.select_one(
                        "span.p13n-sc-truncate, "
                        "span.p13n-sc-truncated, "
                        "div._cDEzb_p13n-sc-css-line-clamp-1_1Fn1y, "
                        "a.a-link-normal span"
                    )
                    precio_el = item.select_one("span.p13n-sc-price, span._cDEzb_p13n-sc-price_1lds4")
                    rating_el = item.select_one("span.a-icon-alt")
                    reviews_el = item.select_one("span.a-size-small")
                    titulo  = titulo_el.get_text(strip=True) if titulo_el else ""
                    precio_txt = precio_el.get_text(strip=True) if precio_el else "$0"
                    rating_txt = rating_el.get_text(strip=True) if rating_el else "0"
                    reviews_txt = reviews_el.get_text(strip=True) if reviews_el else "0"
                    if titulo:
                        productos_cat.append((titulo, precio_txt, rating_txt, reviews_txt))
            else:
                # Regex fallback (menos preciso)
                # Buscar patrones comunes en el HTML de Amazon Best Sellers
                titulos = re.findall(
                    r'class="[^"]*p13n-sc-truncat[^"]*"[^>]*>\s*<span[^>]*>(.*?)</span>',
                    html_text, re.DOTALL
                )
                precios = re.findall(
                    r'class="[^"]*p13n-sc-price[^"]*"[^>]*>(.*?)</span>',
                    html_text, re.DOTALL
                )
                for j, titulo in enumerate(titulos[:30]):
                    titulo_clean = re.sub(r'<[^>]+>', '', titulo).strip()
                    precio_txt   = precios[j] if j < len(precios) else "$0"
                    precio_clean = re.sub(r'<[^>]+>', '', precio_txt).strip()
                    if titulo_clean:
                        productos_cat.append((titulo_clean, precio_clean, "0", "0"))

            # Convertir al formato interno
            nuevos = 0
            for titulo, precio_txt, rating_txt, reviews_txt in productos_cat:
                titulo = re.sub(r'\s+', ' ', titulo).strip()
                if not titulo or len(titulo) < 5:
                    continue
                pid = titulo[:40].lower()
                if pid in vistos:
                    continue
                vistos.add(pid)

                precio = parse_precio(precio_txt)
                rating_m = re.search(r'([\d.]+)', str(rating_txt))
                rating  = float(rating_m.group(1)) if rating_m else 0.0
                reviews_m = re.search(r'([\d,]+)', str(reviews_txt).replace(",", ""))
                reviews = int(reviews_m.group(1).replace(",","")) if reviews_m else 0

                todos.append({
                    "product_title":      titulo,
                    "min_price":          f"${precio:.2f}" if precio else "$20",
                    "_tiene_precio_real": precio > 0,   # Amazon siempre tiene precio real
                    "total_sale_30d_cnt": 500,   # Sin dato real → valor conservador
                    "total_sale_7d_cnt":  100,
                    "influencers_count":  50,
                    "product_rating":     str(rating),
                    "review_count":       str(reviews),
                    "category":           cat_nombre,
                    "_fuente":            f"Amazon/{cat_nombre}",
                    "_amazon_sin_ventas": True,  # Marcar: ventas_30d es estimada
                })
                nuevos += 1

            print(f"{nuevos} nuevos (total: {len(todos)})")

        except Exception as e:
            print(f"⚠ {e}")

        time.sleep(1.5)

    return todos


# ============================================================
# NUVOFINDS — blogs de productos virales curados
# Soporta: Blogger (?alt=json feed) y Shopify (/blogs/... artículo)
# ============================================================
NUVOFINDS_SOURCES = [
    ("NuvoFinds/Home",  "https://www.nuvofinds.com/feeds/posts/default?alt=json&max-results=100"),
    ("KydsChoice/Gold", "https://kydschoice.com/blogs/news/gold-products-so-far"),
    # Agregar más blogs curados acá (Blogger feed o URL artículo Shopify):
    # ("NombreBlog", "https://..."),
]

def _precio_shopify_product(url, h):
    """Extrae precio USD de un producto Shopify via API .json"""
    try:
        if "/products/" not in url:
            return 0.0
        prod_url = url.split("?")[0].rstrip("/") + ".json"
        r = requests.get(prod_url, headers=h, timeout=10)
        if r.status_code == 200:
            variants = r.json().get("product", {}).get("variants", [])
            if variants:
                precio = float(variants[0].get("price", 0))
                if 1.0 < precio < 500.0:
                    return precio
    except Exception:
        pass
    return 0.0


def _parse_shopify_article(url, fuente_nombre, todos, vistos, HEADERS):
    """Parsea un artículo de blog Shopify via API JSON nativa."""
    json_url = url.rstrip("/") + ".json"
    r = requests.get(json_url, headers=HEADERS, timeout=15)
    if r.status_code == 200:
        contenido = r.json().get("article", {}).get("body_html", "")
    else:
        # Fallback: scraping HTML directo
        r2 = requests.get(url, headers={**HEADERS, "Accept": "text/html"}, timeout=15)
        if r2.status_code != 200:
            print(f"HTTP {r2.status_code}")
            return 0
        contenido = r2.text

    from bs4 import BeautifulSoup as _BS
    soup = _BS(contenido, "html.parser")

    nuevos = 0
    _DOMINIOS_AFIL = ("rstyle.me", "go.magik.ly", "amzn.to", "awin1.com", "click.linksynergy")
    for tag in soup.find_all("a"):
        titulo  = re.sub(r'\s+', ' ', tag.get_text(separator=" ", strip=True)).strip()
        href    = tag.get("href", "")
        if len(titulo) < 8 or len(titulo) > 120:
            continue
        if any(x in titulo.lower() for x in ["read more", "click here", "shop now", "buy now",
                                               "view all", "see more", "learn more", "follow",
                                               "instagram", "tiktok"]):
            continue
        pid = titulo[:40].lower()
        if pid in vistos:
            continue
        vistos.add(pid)

        precio  = 0.0
        # Hostname del blog para detectar links a sus propios productos Shopify
        _blog_host = url.split("/")[2] if url.startswith("http") else ""
        url_fin = href if href.startswith("http") else (f"https://{_blog_host}{href}" if href.startswith("/") else "")

        if "amazon." in href.lower():
            precio = _extraer_precio_amazon(href)
        elif "/products/" in href and (_blog_host in href or href.startswith("/")):
            # Link a producto Shopify del mismo blog
            precio = _precio_shopify_product(url_fin, HEADERS)
        elif any(dom in href.lower() for dom in _DOMINIOS_AFIL):
            url_fin = _seguir_redirect(href)
            if "amazon." in url_fin.lower():
                if "/s?" not in url_fin:
                    precio = _extraer_precio_amazon(url_fin)
                else:
                    m_q = re.search(r'[?&]k=([^&]+)', url_fin)
                    if m_q:
                        titulo = urllib.parse.unquote_plus(m_q.group(1))[:80]
            elif "/products/" in url_fin:
                precio = _precio_shopify_product(url_fin, HEADERS)

        todos.append({
            "product_title":      titulo,
            "min_price":          f"${precio:.2f}" if precio else "0",
            "_tiene_precio_real": precio > 0,
            "_precio_real_usd":   precio if precio > 0 else None,
            "total_sale_30d_cnt": 300,
            "total_sale_7d_cnt":  60,
            "influencers_count":  5,
            "product_rating":     "4.5",
            "review_count":       "0",
            "category":           "Curated",
            "_fuente":            f"Blog/{fuente_nombre}",
            "product_url":        url_fin or href,
            "_dias_antiguedad":   30,
        })
        nuevos += 1
    print(f"{nuevos} productos")
    return nuevos


def get_nuvofinds_products():
    """
    Scrapea blogs curados de productos virales.
    Soporta Blogger (feed JSON ?alt=json) y Shopify (artículo /blogs/).
    """
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    todos  = []
    vistos = set()

    for fuente_nombre, feed_url in NUVOFINDS_SOURCES:
        print(f"  🌐 {fuente_nombre}...", end=" ", flush=True)
        try:
            # Detectar tipo: Shopify (/blogs/) vs Blogger (?alt=json)
            if "/blogs/" in feed_url and "alt=json" not in feed_url:
                _parse_shopify_article(feed_url, fuente_nombre, todos, vistos, HEADERS)
                continue

            r = requests.get(feed_url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                print(f"HTTP {r.status_code}")
                continue
            data    = r.json()
            entries = data.get("feed", {}).get("entry", [])
            nuevos  = 0
            for entry in entries:
                titulo = entry.get("title", {}).get("$t", "").strip()
                if not titulo or len(titulo) < 5:
                    continue
                pid = titulo[:40].lower()
                if pid in vistos:
                    continue
                vistos.add(pid)

                # URL del post
                url_post = ""
                for lnk in entry.get("link", []):
                    if lnk.get("rel") == "alternate":
                        url_post = lnk.get("href", "")
                        break

                # Buscar precio: 1) inline en el texto, 2) links Amazon directos, 3) links afiliados
                contenido = entry.get("content", {}).get("$t", "") or \
                            entry.get("summary", {}).get("$t", "")
                precio = 0.0
                m_precio = re.search(r'\$\s*([\d]+(?:\.\d{1,2})?)', contenido)
                if m_precio:
                    precio = float(m_precio.group(1))
                if not precio:
                    amazon_links = _extraer_links_amazon(contenido)
                    for link in amazon_links[:2]:
                        precio = _extraer_precio_amazon(link)
                        if precio:
                            break
                if not precio:
                    afil_links = _extraer_links_afiliados(contenido)
                    for link in afil_links[:3]:
                        url_fin = _seguir_redirect(link)
                        if "amazon." in url_fin.lower() and "/s?" not in url_fin:
                            precio = _extraer_precio_amazon(url_fin)
                            if precio:
                                break

                # Fecha de publicación → más reciente = más trending
                pub = entry.get("published", {}).get("$t", "")
                dias_antiguedad = 999
                try:
                    pub_dt = datetime.fromisoformat(pub[:19])
                    dias_antiguedad = (datetime.now() - pub_dt).days
                except Exception:
                    pass
                # Ventas estimadas: posts más recientes = más señal de trending
                ventas_est = max(800 - dias_antiguedad * 2, 100)
                # Influencers: si tiene precio real en contenido = más confiable
                influencers_est = 20 if precio > 0 else 10

                todos.append({
                    "product_title":      titulo,
                    "min_price":          f"${precio:.2f}" if precio else "0",
                    "_tiene_precio_real": precio > 0,
                    "_precio_real_usd":   precio if precio > 0 else None,
                    "total_sale_30d_cnt": ventas_est,
                    "total_sale_7d_cnt":  ventas_est // 5,
                    "influencers_count":  influencers_est,
                    "product_rating":     "4.5",
                    "review_count":       "0",
                    "category":           "Home/Gadgets",
                    "_fuente":            "NuvoFinds",
                    "product_url":        url_post,
                    "_pub_date":          pub,
                    "_dias_antiguedad":   dias_antiguedad,
                })
                nuevos += 1
            print(f"{nuevos} productos")
        except Exception as e:
            print(f"⚠ {e}")

    return todos


# ============================================================
# INFLUENCERS — beacons.ai / linktree curated picks
# ============================================================
def get_influencer_picks():
    """
    Scrapea las páginas de link-in-bio (beacons.ai, linktr.ee) de cuentas
    de IG que publican productos trending. Extrae nombres de productos y
    links (usualmente Amazon) para incorporarlos como candidatos.

    Para agregar cuentas: editar INFLUENCER_SOURCES al inicio del archivo.
    """
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language":   "en-US,en;q=0.9",
        "Accept-Encoding":   "gzip, deflate, br",
        "Connection":        "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest":    "document",
        "Sec-Fetch-Mode":    "navigate",
        "Sec-Fetch-Site":    "none",
        "Sec-Fetch-User":    "?1",
        "Cache-Control":     "max-age=0",
        "sec-ch-ua":         '"Chromium";v="124", "Google Chrome";v="124"',
        "sec-ch-ua-mobile":  "?0",
        "sec-ch-ua-platform":'"macOS"',
    }

    try:
        from bs4 import BeautifulSoup
        _bs4 = True
    except ImportError:
        _bs4 = False

    todos  = []
    vistos = set()

    for nombre_cuenta, url_base, categoria in INFLUENCER_SOURCES:
        print(f"  📱 {nombre_cuenta} ({url_base.split('/')[2]})...", end=" ", flush=True)
        try:
            r = requests.get(url_base, headers=HEADERS, timeout=15, allow_redirects=True)
            if r.status_code != 200:
                # Fallback: intentar con Playwright (maneja Cloudflare/JS)
                print(f"HTTP {r.status_code} — intentando Playwright...", end=" ", flush=True)
                html_pw = _playwright_get_html(url_base, wait_ms=3500)
                if not html_pw:
                    print("sin Playwright")
                    continue
                html = html_pw
            else:
                html = r.text
            links_encontrados = []   # lista de (titulo, url_destino)

            # ── Prioridad: extraer links reales de __NEXT_DATA__ (beacons.ai es Next.js) ──
            next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>',
                                        html, re.DOTALL)
            if next_data_match:
                try:
                    nd = json.loads(next_data_match.group(1))
                    # Recorrer toda la estructura buscando links con título y URL
                    def _walk(obj, depth=0):
                        if depth > 12 or not obj:
                            return
                        if isinstance(obj, dict):
                            titulo = (obj.get("title") or obj.get("name") or
                                      obj.get("label") or obj.get("text") or "")
                            url    = (obj.get("url") or obj.get("href") or
                                      obj.get("link") or obj.get("destinationUrl") or "")
                            if (isinstance(titulo, str) and isinstance(url, str)
                                    and 8 < len(titulo) < 120
                                    and url.startswith("http")
                                    and titulo not in vistos):
                                vistos.add(titulo)
                                links_encontrados.append((titulo, url))
                            for v in obj.values():
                                _walk(v, depth + 1)
                        elif isinstance(obj, list):
                            for item in obj:
                                _walk(item, depth + 1)
                    _walk(nd)
                except Exception:
                    pass

            if _bs4 and not links_encontrados:
                soup = BeautifulSoup(html, "html.parser")

                # Patrón beacons.ai: links con texto dentro de <a> o <button>
                for tag in soup.find_all(["a", "button"]):
                    href = tag.get("href", "")
                    # Buscar texto significativo
                    texto = tag.get_text(separator=" ", strip=True)
                    texto = re.sub(r'\s+', ' ', texto).strip()

                    # Filtrar ruidos: iconos, botones genéricos, redes sociales
                    if (len(texto) > 8
                            and not any(x in texto.lower() for x in
                                       ["follow", "instagram", "tiktok", "youtube",
                                        "twitter", "facebook", "pinterest", "shop all",
                                        "subscribe", "newsletter", "contact", "about"])
                            and texto not in vistos):
                        vistos.add(texto)
                        links_encontrados.append((texto, href))

            else:
                # Fallback regex: buscar patrones comunes de beacons.ai
                # beacons.ai renderiza links en data-testid o clase beacon-link
                patrones = [
                    r'data-link-title="([^"]{8,80})"',
                    r'"title"\s*:\s*"([^"]{8,80})"',
                    r'class="[^"]*link[^"]*title[^"]*"[^>]*>([^<]{8,80})<',
                    r'<span[^>]*>([A-Z][^<]{8,79})</span>',
                ]
                for patron in patrones:
                    for m in re.finditer(patron, html, re.IGNORECASE):
                        texto = m.group(1).strip()
                        if texto not in vistos and len(texto) > 8:
                            vistos.add(texto)
                            links_encontrados.append((texto, ""))

                # También buscar links a Amazon
                amazon_links = re.findall(
                    r'href="(https?://(?:www\.)?amazon\.com/[^"]{10,200})"',
                    html
                )
                for href in amazon_links:
                    # Extraer nombre del producto del path de Amazon
                    m = re.search(r'/([A-Z][^/]{5,60})/dp/', href)
                    if m:
                        titulo = m.group(1).replace("-", " ").title()
                        if titulo not in vistos:
                            vistos.add(titulo)
                            links_encontrados.append((titulo, href))

            # Convertir al formato interno
            nuevos = 0
            _DOMINIOS_AFILIADOS = ("rstyle.me", "go.magik.ly", "amzn.to", "clk.tradedoubler",
                                   "awin1.com", "click.linksynergy", "imp.i305022", "bit.ly")
            for titulo, href in links_encontrados[:40]:  # max 40 por cuenta
                precio  = 0.0
                url_fin = href

                if href and href.startswith("http"):
                    if "amazon." in href.lower():
                        # Link directo a Amazon
                        precio = _extraer_precio_amazon(href)
                    elif any(dom in href.lower() for dom in _DOMINIOS_AFILIADOS):
                        # Seguir redirect de afiliado
                        url_fin = _seguir_redirect(href)
                        if "amazon." in url_fin.lower():
                            # Si es búsqueda, actualizar título con la query
                            if "/s?" in url_fin and "k=" in url_fin:
                                m_q = re.search(r'[?&]k=([^&]+)', url_fin)
                                if m_q:
                                    titulo_amazon = urllib.parse.unquote_plus(m_q.group(1))
                                    if len(titulo_amazon) > len(titulo):
                                        titulo = titulo_amazon[:80]
                            else:
                                precio = _extraer_precio_amazon(url_fin)

                todos.append({
                    "product_title":       titulo[:80],
                    "min_price":           f"${precio:.2f}" if precio else "0",
                    "_tiene_precio_real":  precio > 0,
                    "_precio_real_usd":    precio if precio > 0 else None,
                    "total_sale_30d_cnt":  200,
                    "total_sale_7d_cnt":   0,
                    "influencers_count":   1,
                    "product_rating":      "4.5",
                    "review_count":        "50",
                    "category":            categoria,
                    "_fuente":             f"IG/{nombre_cuenta}",
                    "_influencer":         True,
                    "_url_ig":             url_base,
                    "product_url":         url_fin if url_fin and url_fin.startswith("http") else (href if href.startswith("http") else ""),
                })
                nuevos += 1

            print(f"{nuevos} productos")

        except Exception as e:
            print(f"⚠ {e}")

        time.sleep(1)

    return todos


# ============================================================
# ALIEXPRESS — FUENTE CHINA (precio real + trending por categoría)
# ============================================================
def get_banggood_trending():
    """
    Scrapea Banggood bestsellers — marketplace chino con precios de fábrica.
    Mucho menos protegido que AliExpress.
    """
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    URLS = [
        ("Best Sellers",  "https://www.banggood.com/best-sellers/"),
        ("Hot Products",  "https://www.banggood.com/hot-products/"),
        ("Home & Garden", "https://www.banggood.com/best-sellers/home-garden/"),
        ("Beauty",        "https://www.banggood.com/best-sellers/health-beauty/"),
        ("Sports",        "https://www.banggood.com/best-sellers/sports-fitness/"),
        ("Pets",          "https://www.banggood.com/best-sellers/pet-products/"),
    ]
    todos  = []
    vistos = set()
    print("  🇨🇳 Banggood...", end=" ", flush=True)
    total_nuevos = 0

    def _parse_banggood_html(html, cat_nombre):
        nonlocal total_nuevos
        from bs4 import BeautifulSoup as _BS
        soup = _BS(html, "html.parser")

        # Debug: si no encontramos nada, guardar HTML para inspección
        selectors = [
            # Selectores nuevos basados en estructura real observada
            ".product-list-item", ".goods-item", ".goodsItem",
            "[class*='goodsList'] li", "[class*='goods-list'] li",
            ".list-item", ".pro-item",
            # Selectores anteriores
            ".product-list-inner li", ".goodListItem",
            "[class*='product_item']", "[class*='product-item']",
            "li.item", ".card-product",
        ]
        cards = []
        for sel in selectors:
            cards = soup.select(sel)
            if cards:
                break

        if not cards and cat_nombre == "Best Sellers":
            # Guardar HTML para debug
            _debug_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_banggood_debug.html")
            with open(_debug_path, "w", encoding="utf-8") as _f:
                _f.write(html)
            # Mostrar las primeras clases únicas encontradas para ayudar a encontrar selectores
            all_classes = set()
            for tag in soup.find_all(True, limit=200):
                for cls in tag.get("class", []):
                    all_classes.add(cls)
            clase_muestra = [c for c in sorted(all_classes) if "product" in c.lower() or "goods" in c.lower() or "item" in c.lower() or "list" in c.lower()]
            print(f"\n    ⚠ Banggood: 0 cards. Clases relevantes: {clase_muestra[:15]}")
            print(f"    → HTML guardado en _banggood_debug.html para inspección")

        for card in cards:
            t_el = card.select_one(
                ".goods-name, .product-title, [class*='title'], [class*='name'], h3, p.name"
            )
            p_el = card.select_one(".main-price, [class*='main-price'], .price, [class*='price']")
            if not t_el:
                continue
            titulo = t_el.get_text(strip=True)
            if not titulo or len(titulo) < 5:
                continue
            pid = titulo[:40].lower()
            if pid in vistos:
                continue
            vistos.add(pid)
            precio = parse_precio(p_el.get_text(strip=True) if p_el else "0")
            if precio > 0 and (precio < MIN_PRECIO_USD or precio > MAX_PRECIO_USD):
                continue
            todos.append({
                "product_title":      titulo,
                "min_price":          f"${precio:.2f}" if precio else "0",
                "_tiene_precio_real": precio > 0,
                "total_sale_30d_cnt": 200,
                "total_sale_7d_cnt":  40,
                "influencers_count":  5,
                "product_rating":     "4.3",
                "review_count":       "50",
                "category":           cat_nombre,
                "_fuente":            "Banggood",
                "_aliexpress":        True,
                "_precio_real_usd":   precio if precio > 0 else None,
                "_orders_total":      200,
            })
            total_nuevos += 1

    # Playwright multi-step: primero homepage para establecer dominio, luego setear cookies
    # y finalmente navegar a las categorías. Así Banggood no muestra el geo-selector.
    def _banggood_playwright_multistep(urls_cats):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                          "--disable-blink-features=AutomationControlled"],
                )
                ctx = browser.new_context(
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
                    locale="en-US", viewport={"width": 1280, "height": 900},
                    extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                )
                page = ctx.new_page()
                page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

                # Paso 1: homepage para establecer cookies del dominio
                try:
                    page.goto("https://www.banggood.com/", wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                except Exception:
                    pass

                # Paso 2: sobreescribir cookies de país
                ctx.add_cookies([
                    {"name": "ship_country",  "value": "US",  "domain": ".banggood.com", "path": "/"},
                    {"name": "currency",      "value": "USD", "domain": ".banggood.com", "path": "/"},
                    {"name": "currency_code", "value": "USD", "domain": ".banggood.com", "path": "/"},
                ])

                # Paso 3: cerrar modal de geo-selector si sigue visible
                try:
                    page.evaluate("""
                        const closeBtn = document.querySelector(
                            '.js-close-ship-to, [class*="close"][class*="ship"],
                             [class*="shipto"] button, .shipto-listWrap .close,
                             .modal-close, .js-close'
                        );
                        if (closeBtn) closeBtn.click();
                    """)
                except Exception:
                    pass

                # Paso 4: navegar a cada categoría y parsear
                for cat_nombre, url in urls_cats:
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(5000)
                        # Cerrar modal si aparece de nuevo
                        try:
                            page.evaluate("""
                                const b = document.querySelector('[class*="shipto"] button, .js-close-ship-to');
                                if (b) b.click();
                            """)
                            page.wait_for_timeout(500)
                        except Exception:
                            pass
                        _parse_banggood_html(page.content(), cat_nombre)
                    except Exception as e2:
                        print(f"\n    [Banggood] {cat_nombre}: {e2}")
                browser.close()
        except Exception as e:
            print(f"[Banggood Playwright] {e}")

    _banggood_playwright_multistep(URLS[:3])

    print(f"{total_nuevos} productos")
    return todos


def get_aliexpress_trending():
    """
    Busca productos trending en AliExpress ordenados por ventas.
    Usa sesión con warm-up de cookies + API interna glosearch + fallback HTML.
    Ventaja clave: devuelve el PRECIO REAL de importación, no una estimación.
    """
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer":          "https://www.aliexpress.com/",
        "Accept":           "application/json, text/html, */*",
        "Accept-Language":  "en-US,en;q=0.9",
        "Accept-Encoding":  "gzip, deflate, br",
        "sec-ch-ua":        '"Chromium";v="124", "Google Chrome";v="124"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest":   "empty",
        "Sec-Fetch-Mode":   "cors",
        "Sec-Fetch-Site":   "same-origin",
    }

    # Warm-up: cargar homepage para obtener cookies de sesión
    session = requests.Session()
    try:
        session.get("https://www.aliexpress.com/", headers={
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
        }, timeout=15)
    except Exception:
        pass  # Si falla el warm-up, igual intentamos con lo que hay

    todos  = []
    vistos = set()

    for cat_nombre, keywords in ALIEXPRESS_CATEGORIAS:
        print(f"  🇨🇳 AliExpress '{cat_nombre}'...", end=" ", flush=True)
        productos_cat = []

        # ── Intento 1: API JSON interna (con sesión/cookies) ─────────────
        try:
            r = session.get(
                "https://www.aliexpress.com/glosearch/api/product",
                params={
                    "keywords":   keywords,
                    "SortType":   "total_tranpro_desc",
                    "page":       1,
                    "pageSize":   30,
                    "currency":   "USD",
                    "locale":     "en_US",
                },
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code == 200 and r.text.strip().startswith("{"):
                data = r.json()
                # Navegar la estructura (puede variar según versión)
                raw_list = (
                    data.get("data", {})
                        .get("products", {})
                        .get("productList", [])
                    or data.get("result", {})
                        .get("mods", {})
                        .get("itemList", {})
                        .get("content", [])
                    or []
                )
                for item in raw_list:
                    prod = item.get("product", item)
                    titulo = prod.get("title", prod.get("name", ""))
                    if not titulo:
                        continue

                    # Precio real en USD
                    precio = 0.0
                    prices = prod.get("prices", {})
                    sale   = prices.get("salePrice", prices.get("originalPrice", {}))
                    if isinstance(sale, dict):
                        precio = float(sale.get("value", 0) or 0)
                    if precio == 0:
                        precio = parse_precio(str(prod.get("price", "0")))

                    # Órdenes totales
                    trade = str(prod.get("tradeDesc", prod.get("orders", "0")))
                    orders_total = parse_num(re.sub(r'[^0-9KkMm+]', '', trade))

                    # Rating y reseñas
                    ev     = prod.get("evaluation", {})
                    rating  = float(ev.get("starRating", 0) if isinstance(ev, dict) else 0)
                    reviews = parse_num(str(ev.get("totalEvaluationCount", 0) if isinstance(ev, dict) else 0))

                    # URL
                    url = prod.get("productDetailUrl", "")
                    if url and not url.startswith("http"):
                        url = "https:" + url
                    pid_ali = str(prod.get("productId", ""))
                    if not url and pid_ali:
                        url = f"https://www.aliexpress.com/item/{pid_ali}.html"

                    productos_cat.append((titulo, precio, orders_total, rating, reviews, url))

        except Exception:
            pass

        # ── Intento 2: scraping HTML con window.runParams ─────────────────
        if not productos_cat:
            try:
                search_url = (
                    f"https://www.aliexpress.com/wholesale"
                    f"?SearchText={requests.utils.quote(keywords)}"
                    f"&SortType=total_tranpro_desc&page=1"
                )
                r2 = session.get(search_url, headers=HEADERS, timeout=15)
                if r2.status_code == 200:
                    m = re.search(
                        r'window\.runParams\s*=\s*(\{.{100,}\});\s*(?:window\.|</script>)',
                        r2.text, re.DOTALL
                    )
                    if m:
                        rp   = json.loads(m.group(1))
                        content = (
                            rp.get("data", {})
                              .get("result", {})
                              .get("mods", {})
                              .get("itemList", {})
                              .get("content", [])
                        )
                        for item in content:
                            titulo = item.get("title", {}).get("displayTitle", "")
                            if not titulo:
                                continue
                            precio = float(
                                item.get("prices", {})
                                    .get("salePrice", {})
                                    .get("minPrice", 0) or 0
                            )
                            trade_obj = item.get("trade", {})
                            orders_total = parse_num(
                                str(trade_obj.get("realTradeCount", 0))
                            )
                            rating  = float(item.get("evaluation", {}).get("starRating", 0) or 0)
                            reviews = parse_num(
                                str(item.get("evaluation", {}).get("totalEvaluationCount", 0))
                            )
                            pid_ali = str(item.get("productId", ""))
                            url = f"https://www.aliexpress.com/item/{pid_ali}.html" if pid_ali else ""
                            productos_cat.append((titulo, precio, orders_total, rating, reviews, url))
            except Exception:
                pass

        # ── Intento 3: Playwright (si Cloudflare bloqueó los dos anteriores) ─
        if not productos_cat:
            search_url_pw = (
                f"https://www.aliexpress.com/wholesale"
                f"?SearchText={requests.utils.quote(keywords)}"
                f"&SortType=total_tranpro_desc&page=1"
            )
            print("(Playwright)...", end=" ", flush=True)
            html_pw = _playwright_get_html(search_url_pw, wait_ms=4000)
            if html_pw:
                try:
                    from bs4 import BeautifulSoup as _BS
                    soup_pw = _BS(html_pw, "html.parser")
                    for card in soup_pw.select("[class*='product-snippet'], [class*='list--gallery']  > div, article"):
                        t_el = card.select_one("[class*='title'], h1, h2, h3")
                        p_el = card.select_one("[class*='price'], [class*='Price']")
                        if not t_el:
                            continue
                        titulo_pw = t_el.get_text(strip=True)
                        precio_pw = parse_precio(p_el.get_text(strip=True) if p_el else "0")
                        if titulo_pw and len(titulo_pw) > 5:
                            productos_cat.append((titulo_pw, precio_pw, 100, 0.0, 0, ""))
                except Exception:
                    pass

        # ── Convertir al formato interno ──────────────────────────────────
        nuevos = 0
        for titulo, precio, orders_total, rating, reviews, url in productos_cat:
            titulo = re.sub(r'\s+', ' ', titulo).strip()
            if not titulo or len(titulo) < 5:
                continue
            pid = titulo[:40].lower()
            if pid in vistos:
                continue
            vistos.add(pid)

            # Estimar ventas mensuales desde total (rough: total/12 meses de vida)
            ventas_30d_est = max(int(orders_total / 12), 20)

            todos.append({
                "product_title":       titulo,
                "min_price":           f"${precio:.2f}" if precio else "$15",
                "total_sale_30d_cnt":  ventas_30d_est,
                "total_sale_7d_cnt":   0,
                "influencers_count":   1,
                "product_rating":      str(rating),
                "review_count":        str(reviews),
                "category":            cat_nombre,
                "_fuente":             "AliExpress",
                "_aliexpress":         True,
                "_orders_total":       orders_total,
                "_precio_real_usd":    precio,   # precio REAL de importación
                "product_url":         url,
            })
            nuevos += 1

        if not productos_cat:
            print("precio estimado (AliExpress bloqueado)")
        else:
            print(f"{nuevos} productos")

        time.sleep(1.5)

    return todos


# ============================================================
# FILTRAR POR DEMANDA ORGÁNICA
# ============================================================
def filtrar_productos(productos):
    vistos    = set()
    filtrados = []

    for p in productos:
        if not isinstance(p, dict):
            continue

        titulo = _campo(p, ["product_title", "product_name", "title", "name"], "")
        if not titulo:
            continue

        # Excluir productos médicos/movilidad/no viables
        titulo_lower = titulo.lower()
        if any(excl in titulo_lower for excl in PALABRAS_EXCLUIR):
            continue

        pid = _campo(p, ["product_id", "group_id"], titulo[:30])
        if pid in vistos:
            continue
        vistos.add(pid)

        precio      = parse_precio(_campo(p, ["min_price", "real_price", "min_price_fz"], None))
        ventas_30d  = parse_num(_campo(p, ["total_sale_30d_cnt"], None))
        ventas_7d   = parse_num(_campo(p, ["total_sale_7d_cnt"], None))
        ventas_total = parse_num(_campo(p, ["total_sale_cnt"], None))
        influencers  = parse_num(_campo(p, ["influencers_count", "total_ifl_cnt", "creator_count"], None))
        rating       = float(_campo(p, ["product_rating", "rating"], 0) or 0)
        reviews      = parse_num(_campo(p, ["review_count", "review_cnt"], None))
        categoria    = _campo(p, ["category", "categories"], "")
        comision     = _campo(p, ["commission"], "")
        lives_s      = parse_num(_campo(p, ["lives_sales"], None))
        videos_s     = parse_num(_campo(p, ["videos_sales"], None))
        url_prod     = _campo(p, ["product_url", "url"], "")
        if not url_prod:
            raw_id = _campo(p, ["product_id", "group_id"], "")
            if raw_id:
                url_prod = f"https://shop.tiktok.com/view/product/{raw_id}"

        # Filtros de demanda y precio
        if precio < MIN_PRECIO_USD or precio > MAX_PRECIO_USD:
            continue
        if ventas_30d < MIN_SALES_30D:
            continue

        ratio = round(ventas_30d / max(influencers, 1), 2)
        if ratio < MIN_RATIO_VENTA:
            continue

        # Restricciones regulatorias
        nivel_restriccion, desc_restriccion = check_restricciones(titulo, str(categoria))

        filtrados.append({
            "nombre":             titulo[:80],
            "categoria":          str(categoria)[:50],
            "fuente":             p.get("_fuente", "TikTok/US"),
            "ventas_estimadas":   bool(
                p.get("_amazon_sin_ventas") or
                p.get("_aliexpress") or
                p.get("_fuente", "").startswith(("NuvoFinds", "IG/", "Walmart", "Temu"))
            ),
            "precio_usd":         round(precio, 2),
            "_tiene_precio_real": bool(p.get("_tiene_precio_real", precio > 0)),
            "_precio_real_usd":   p.get("_precio_real_usd"),   # AliExpress: precio real
            "_orders_total":      p.get("_orders_total", 0),   # AliExpress: órdenes totales
            "_aliexpress":        bool(p.get("_aliexpress")),
            "influencers":        influencers,
            "ventas_30d":         ventas_30d,
            "ventas_7d":          ventas_7d,
            "ventas_total":       ventas_total,
            "lives_sales":        lives_s,
            "videos_sales":       videos_s,
            "ratio_efic":         ratio,
            "rating":             round(rating, 1),
            "n_reviews":          reviews,
            "comision_tkt":       comision,
            "url":                url_prod,
            "restriccion_nivel":  nivel_restriccion,
            "restriccion_desc":   desc_restriccion,
        })

    filtrados.sort(key=lambda x: x["ratio_efic"], reverse=True)
    return filtrados


# ============================================================
# MERCADOLIBRE — BÚSQUEDA EN ARGENTINA
# ============================================================
_CAT_A_QUERY = {
    "Peelers & Cutters":                         "pelapapas cocina acero",
    "Mouthwash":                                 "enjuague bucal blanqueador",
    "Teeth Whitening":                           "tiras blanqueadoras dientes",
    "Skin Care Kits":                            "crema coreana colageno facial",
    "Facial Sunscreen & Sun Care":               "protector solar facial spf",
    "Bras":                                      "corpiño sin costuras",
    "Vitamins, Minerals & Wellness Supplements": "suplemento vitaminas minerales",
    "Hair Care":                                 "cuidado cabello shampoo",
    "Makeup":                                    "maquillaje cosmética",
    "Essential Oils & Diffusers":                "aceite esencial difusor aromaterapia",
    "Phone Cases":                               "funda celular",
    "LED Lights":                                "tira luz led rgb",
    "Kitchen Gadgets":                           "utensilio cocina gadget",
    "Pet Supplies":                              "accesorio mascotas",
    "Fitness Equipment":                         "accesorio fitness ejercicio",
    "Desk Accessories":                          "organizador escritorio",
    "Travel Accessories":                        "accesorio viaje",
    "Cleaning Products":                         "producto limpieza hogar",
    "Home Organization":                         "organizador hogar",
    "Drink Mixes":                               "bebida suplemento proteína",
}

_KW_A_QUERY = [
    (["peeler", "peeling"],                    "pelapapas"),
    (["mouthwash"],                            "enjuague bucal blanqueador"),
    (["whitening strip", "whitening strips"],  "tiras blanqueadoras dientes"),
    (["whitening"],                            "blanqueador dental"),
    (["collagen balm", "collagen cream"],      "crema colageno facial"),
    (["collagen sunscreen"],                   "protector solar colageno"),
    (["sunscreen", "sun care", "spf"],         "protector solar facial"),
    (["collagen"],                             "suplemento colageno"),
    (["magnesium"],                            "suplemento magnesio"),
    (["supplement", "vitamins", "vitamin"],    "suplemento vitaminas"),
    (["bra", "bras"],                          "corpiño sin costuras"),
    (["drink mix", "energy drink"],            "bebida energetica suplemento"),
    (["serum"],                                "serum facial"),
    (["moisturizer", "moisturizing"],          "crema hidratante facial"),
    (["face roller"],                          "rodillo facial"),
    (["eye mask", "eye massager"],             "mascara ojos relax"),
    (["neck massager"],                        "masajeador cervical"),
    (["massage gun"],                          "pistola masaje muscular"),
    (["resistance band"],                      "banda elastica ejercicio"),
    (["posture corrector"],                    "corrector postura"),
    (["ab roller"],                            "rueda abdominal"),
    (["led light", "led strip"],               "tira led rgb"),
    (["organizer"],                            "organizador"),
    (["cleaner", "cleaning"],                  "limpiador"),
    (["phone stand", "phone holder"],          "soporte celular"),
    (["laptop stand"],                         "soporte notebook"),
    (["wireless charger"],                     "cargador inalambrico"),
    (["silk pillowcase"],                      "funda almohada seda"),
    (["portable blender"],                     "licuadora portatil"),
    (["travel pillow"],                        "almohada viaje"),
    (["car organizer"],                        "organizador auto"),
    (["dog brush"],                            "cepillo perro"),
    (["cat toy"],                              "juguete gato"),
    (["pet hair remover"],                     "quitapelos mascotas"),
    (["phone case"],                           "funda celular"),
    (["pet", "dog", "cat"],                    "accesorio mascotas"),
    (["fitness", "workout"],                   "accesorio fitness"),
    (["travel"],                               "accesorio viaje"),
    (["kitchen"],                              "utensilio cocina"),
    (["hair growth"],                          "crecimiento cabello"),
    (["teeth"],                                "cuidado dental"),
    (["chopper"],                              "picadora verduras"),
    (["air fryer"],                            "freidora sin aceite accesorio"),
]


def query_para_meli(nombre, categoria=""):
    nombre_lower    = nombre.lower()
    categoria_lower = str(categoria).lower()

    for cat, query in _CAT_A_QUERY.items():
        if cat.lower() in categoria_lower or categoria_lower in cat.lower():
            return query

    for kws, query in _KW_A_QUERY:
        for kw in kws:
            if kw in nombre_lower:
                return query

    s     = re.sub(r'\[.*?\]', '', nombre_lower)
    s     = re.sub(r'[|–—].*', '', s)
    words = [w for w in s.split() if len(w) > 3][:3]
    return ' '.join(words) if words else nombre[:30]


def _buscar_meli(query, limit=10):
    if not MELI_BUSQUEDA_ACTIVA or not MELI_ACCESS_TOKEN:
        return -1, []
    return -1, []


def check_meli(nombre_producto, categoria=""):
    query1 = query_para_meli(nombre_producto, categoria)

    if not MELI_ACCESS_TOKEN:
        return {
            "competidores_meli": -1,
            "precio_prom_ars":   0,
            "precio_prom_usd":   0,
            "nivel_competencia": "SIN TOKEN ⚪",
            "query_meli":        query1,
        }

    try:
        total, precios_ars = _buscar_meli(query1)
        if not precios_ars:
            query2 = ' '.join(query1.split()[:2])
            if query2 and query2 != query1:
                total2, precios2 = _buscar_meli(query2)
                if precios2:
                    total, precios_ars = total2, precios2

        precio_prom_ars = sum(precios_ars) / len(precios_ars) if precios_ars else 0
        precio_prom_usd = round(precio_prom_ars / TASA_USD_ARS, 2)
        nivel = ("SIN DATOS ⚪" if total < 0 else
                 "BAJA 🟢" if total < 20 else
                 "MEDIA 🟡" if total < 100 else "ALTA 🔴")
        return {
            "competidores_meli": total,
            "precio_prom_ars":   round(precio_prom_ars),
            "precio_prom_usd":   precio_prom_usd,
            "nivel_competencia": nivel,
            "query_meli":        query1,
        }
    except Exception as e:
        return {
            "competidores_meli": -1, "precio_prom_ars": 0,
            "precio_prom_usd": 0, "nivel_competencia": "ERROR", "query_meli": str(e)[:40],
        }


# ============================================================
# CALCULADORA DE MARGEN
# ============================================================
def calcular_margen(precio_tiktok_usd, precio_meli_usd, precio_alibaba_real=None):
    """
    precio_alibaba_real: precio real de AliExpress (si viene de esa fuente).
    Si no, se estima como RATIO_ALIBABA × precio TikTok.
    """
    if not precio_tiktok_usd and not precio_alibaba_real:
        return None

    if precio_alibaba_real and precio_alibaba_real > 0:
        costo_alibaba = round(precio_alibaba_real, 2)
    else:
        costo_alibaba = round((precio_tiktok_usd or 0) * RATIO_ALIBABA, 2)
    cif           = costo_alibaba + FLETE_AEREO_USD
    iva           = cif * IVA_ARGENTINA
    derechos      = cif * DERECHOS_ADUANA
    costo_total   = round(cif + iva + derechos, 2)

    precio_estimado = False
    if not precio_meli_usd or precio_meli_usd <= 0:
        precio_meli_usd = round(costo_total * 4.0, 2)
        precio_estimado = True

    ingreso_neto  = precio_meli_usd * (1 - COMISION_MELI)
    margen_neto   = round(ingreso_neto - costo_total, 2)
    multiplicador = round(precio_meli_usd / costo_total, 2) if costo_total > 0 else 0

    return {
        "precio_tiktok_usd":  round(precio_tiktok_usd, 2),
        "costo_alibaba_usd":  costo_alibaba,
        "flete_usd":          FLETE_AEREO_USD,
        "iva_usd":            round(iva, 2),
        "costo_total_usd":    costo_total,
        "precio_venta_usd":   round(precio_meli_usd, 2),
        "precio_estimado":    precio_estimado,
        "margen_neto_usd":    margen_neto,
        "multiplicador":      multiplicador,
        "viable":             multiplicador >= MULTIPLICADOR_MINIMO and margen_neto > 0,
    }


# ============================================================
# SCORE FINAL (0-100) — incluye trending MeLi + restricciones
# ============================================================
def calcular_score(producto, meli, margen):
    score = 0

    # Demanda — ventas 30 días (máx 35 pts)
    v30 = producto["ventas_30d"]
    if producto.get("ventas_estimadas"):
        score += 8   # Amazon/AliExpress: sin dato 30d exacto
    elif v30 >= 5000:   score += 35
    elif v30 >= 1000:   score += 25
    elif v30 >= 500:    score += 15
    elif v30 >= 100:    score += 8

    # ── BONUS NOVEDAD (máx +10 pts) ──────────────────────────────────────
    # Muchas ventas con pocas reseñas = producto NUEVO explotando.
    # Muchas reseñas con ventas normales = producto ESTABLECIDO (commodity).
    reviews = max(producto.get("n_reviews", 0), 1)
    if not producto.get("ventas_estimadas"):
        # TikTok: ventas_30d reales
        novelty = v30 / reviews
        if novelty >= 100: score += 10   # muy nuevo y viral
        elif novelty >= 20: score += 7
        elif novelty >= 5:  score += 3
        elif novelty < 0.5: score -= 5   # producto establecido, mucha comp.
    elif producto.get("_aliexpress"):
        # AliExpress: usar total de órdenes vs. reseñas
        orders = max(producto.get("_orders_total", 0), 1)
        novelty_ali = orders / reviews
        if novelty_ali >= 200: score += 10
        elif novelty_ali >= 50: score += 7
        elif novelty_ali >= 10: score += 3

    # Eficiencia orgánica — ventas por influencer (máx 15 pts)
    ratio = producto["ratio_efic"]
    if ratio >= 2.0:   score += 15
    elif ratio >= 0.5: score += 10
    elif ratio >= 0.1: score += 5

    # Calidad del producto (máx 10 pts)
    if producto["rating"] >= 4.5 and producto["n_reviews"] >= 100: score += 10
    elif producto["rating"] >= 4.0: score += 5

    # Competencia en MeLi Argentina (máx 15 pts)
    # comp=-1 significa sin token/sin datos → no sumar puntos
    comp = meli["competidores_meli"]
    if comp >= 0:
        if comp < 20:    score += 15
        elif comp < 100: score += 10
        elif comp < 500: score += 5

    # Margen (máx 15 pts)
    if margen:
        if margen["viable"]:              score += 9
        if margen["multiplicador"] >= 4:  score += 6

    # ── BONUS: trending en MeLi Argentina (máx +10 pts) ──────────────────
    trending_match, trend_kw = _match_trending(
        producto["nombre"], producto.get("categoria", "")
    )
    if trending_match:
        score += 10
        producto["_trending_match"] = trend_kw   # guardar para el reporte
    else:
        producto["_trending_match"] = ""

    # ── PENALIDAD por restricciones regulatorias ──────────────────────────
    nivel_r = producto.get("restriccion_nivel", "OK ✅")
    if "BLOQUEADO" in nivel_r:
        score -= 25
    elif "COMPLEJO" in nivel_r:
        score -= 15
    elif "MODERADO" in nivel_r:
        score -= 5

    return max(score, 0)


# ============================================================
# EVALUACIÓN COMPLETA DE UN PRODUCTO
# ============================================================
def evaluar_producto(producto, tasa_usd):
    global TASA_USD_ARS
    TASA_USD_ARS = tasa_usd
    meli   = check_meli(producto["nombre"], producto.get("categoria", ""))
    time.sleep(2)
    margen = calcular_margen(
        producto["precio_usd"],
        meli["precio_prom_usd"],
        precio_alibaba_real=producto.get("_precio_real_usd"),
    )
    score  = calcular_score(producto, meli, margen)
    precio_venta = margen["precio_venta_usd"] if margen else 0
    return {
        **producto,
        **meli,
        "costo_alibaba_usd": margen["costo_alibaba_usd"] if margen else "N/A",
        "costo_total_usd":   margen["costo_total_usd"]   if margen else "N/A",
        "margen_neto_usd":   margen["margen_neto_usd"]   if margen else "N/A",
        "precio_prom_usd":   precio_venta,
        "precio_prom_ars":   round(precio_venta * TASA_USD_ARS),
        "precio_estimado":   margen["precio_estimado"]   if margen else True,
        "multiplicador":     margen["multiplicador"]     if margen else 0,
        "viable":            margen["viable"]            if margen else False,
        "score":             score,
    }


# ============================================================
# PREVIEW HTML — mock de publicación MeLi para los top productos
# ============================================================
def generar_preview_html(top_productos):
    """Genera un HTML con preview de cómo se vería cada producto en MeLi."""
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    html_path = os.path.join(OUTPUT_DIR, "preview_meli.html")

    cards = ""
    for i, p in enumerate(top_productos[:5], 1):
        nombre       = p.get("nombre", "")[:60]
        precio_ars   = p.get("precio_prom_ars", 0)
        precio_usd   = p.get("precio_prom_usd", 0)
        costo_total  = p.get("costo_total_usd", 0)
        mult         = p.get("multiplicador", 0)
        score        = p.get("score", 0)
        ventas_30d   = p.get("ventas_30d", 0)
        rating       = p.get("rating", 0)
        reviews      = p.get("n_reviews", 0)
        restriccion  = p.get("restriccion_nivel", "OK ✅")
        rest_desc    = p.get("restriccion_desc", "")
        viable       = p.get("viable", False)
        estimado     = p.get("precio_estimado", True)
        trending     = p.get("_trending_match", "")
        query_meli   = p.get("query_meli", "")
        url_tiktok   = p.get("url", "#")
        costo_alibaba = p.get("costo_alibaba_usd", 0)

        estrellas    = "⭐" * int(rating) + ("½" if rating % 1 >= 0.5 else "")
        tag_precio   = " <small style='color:#888'>(precio estimado)</small>" if estimado else ""
        tag_trending = f"<span style='background:#e8f5e9;color:#2e7d32;padding:2px 8px;border-radius:12px;font-size:12px'>📈 Trending MeLi: {trending}</span>" if trending else ""
        badge_viable = "<span style='background:#1a73e8;color:white;padding:3px 10px;border-radius:4px;font-size:12px'>VIABLE ✅</span>" if viable else "<span style='background:#e0e0e0;color:#555;padding:3px 10px;border-radius:4px;font-size:12px'>MARGEN BAJO</span>"

        rest_color = "#f44336" if "BLOQUEADO" in restriccion else ("#ff9800" if "COMPLEJO" in restriccion else ("#2196f3" if "MODERADO" in restriccion else "#4caf50"))

        cards += f"""
        <div class="card">
            <div class="card-rank">#{i}</div>
            <div class="card-score">Score {score}/100</div>
            <h2 class="card-title">{nombre}</h2>
            <div style="margin:6px 0">{tag_trending} {badge_viable}</div>

            <div class="mock-listing">
                <div class="listing-label">🛒 Así se vería en MercadoLibre Argentina:</div>
                <div class="listing-title">{nombre}</div>
                <div class="listing-price">
                    $ {int(precio_ars):,}{tag_precio}
                    <span class="listing-usd">≈ USD {precio_usd}</span>
                </div>
                <div class="listing-condition">Nuevo · 3 disponibles · Envío a todo el país</div>
                <div class="listing-desc">
                    ✅ Producto importado directamente del fabricante, con garantía de calidad.<br>
                    📦 Envíos a todo el país · 💬 Consulte por colores y modelos disponibles
                </div>
                <div class="listing-meta">
                    Búsqueda sugerida en MeLi: <em>"{query_meli}"</em>
                </div>
            </div>

            <table class="metrics">
                <tr>
                    <td>💰 Precio TikTok USA</td>
                    <td><strong>USD {p.get('precio_usd', 0)}</strong></td>
                </tr>
                <tr>
                    <td>🏭 Alibaba estimado</td>
                    <td><strong>USD {costo_alibaba}</strong></td>
                </tr>
                <tr>
                    <td>📦 Costo total importado</td>
                    <td><strong>USD {costo_total}</strong> (Alibaba + flete + IVA + derechos)</td>
                </tr>
                <tr>
                    <td>📊 Multiplicador</td>
                    <td><strong>{mult}x</strong></td>
                </tr>
                <tr>
                    <td>📈 Ventas TikTok 30d</td>
                    <td><strong>{int(ventas_30d):,} unidades</strong></td>
                </tr>
                <tr>
                    <td>⭐ Rating TikTok</td>
                    <td><strong>{rating} {estrellas}</strong> ({int(reviews):,} reseñas)</td>
                </tr>
            </table>

            <div class="restriccion" style="border-left:4px solid {rest_color}">
                <strong>Estado regulatorio:</strong> {restriccion}<br>
                <small>{rest_desc}</small>
            </div>

            <a href="{url_tiktok}" target="_blank" class="btn-tiktok">Ver en TikTok Shop →</a>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Preview MeLi — Top Productos {datetime.now().strftime('%Y-%m-%d')}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #f5f5f5; color: #333; padding: 20px; }}
        h1 {{ color: #3483fa; margin-bottom: 4px; }}
        .subtitle {{ color: #666; margin-bottom: 24px; font-size: 14px; }}
        .grid {{ display: flex; flex-direction: column; gap: 24px; max-width: 800px; margin: 0 auto; }}
        .card {{ background: white; border-radius: 12px; padding: 24px;
                 box-shadow: 0 2px 8px rgba(0,0,0,0.1); position: relative; }}
        .card-rank {{ position: absolute; top: 16px; right: 60px; font-size: 28px;
                      font-weight: bold; color: #eee; }}
        .card-score {{ position: absolute; top: 16px; right: 16px; font-size: 13px;
                       color: #888; }}
        .card-title {{ font-size: 18px; font-weight: 600; margin-bottom: 10px;
                        color: #111; line-height: 1.3; }}
        .mock-listing {{ background: #f8faff; border: 1px solid #d0e4ff;
                          border-radius: 8px; padding: 16px; margin: 16px 0; }}
        .listing-label {{ font-size: 11px; color: #888; margin-bottom: 8px;
                           text-transform: uppercase; letter-spacing: 0.5px; }}
        .listing-title {{ font-size: 16px; color: #333; margin-bottom: 8px; font-weight: 500; }}
        .listing-price {{ font-size: 28px; color: #333; font-weight: 700; margin-bottom: 4px; }}
        .listing-usd {{ font-size: 14px; color: #888; margin-left: 8px; font-weight: normal; }}
        .listing-condition {{ font-size: 13px; color: #00a650; margin-bottom: 10px; }}
        .listing-desc {{ font-size: 13px; color: #555; margin-bottom: 10px;
                          background: white; padding: 10px; border-radius: 6px;
                          line-height: 1.6; }}
        .listing-meta {{ font-size: 12px; color: #888; }}
        .metrics {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }}
        .metrics td {{ padding: 6px 4px; border-bottom: 1px solid #f0f0f0; }}
        .metrics td:first-child {{ color: #666; width: 55%; }}
        .restriccion {{ background: #f9f9f9; padding: 10px 12px; border-radius: 6px;
                         margin: 12px 0; font-size: 13px; line-height: 1.5; }}
        .btn-tiktok {{ display: inline-block; margin-top: 12px; padding: 8px 16px;
                        background: #ff2d55; color: white; text-decoration: none;
                        border-radius: 6px; font-size: 13px; font-weight: 500; }}
        .btn-tiktok:hover {{ background: #e0002a; }}
        .header {{ max-width: 800px; margin: 0 auto 24px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🛒 Preview de Publicaciones — MercadoLibre Argentina</h1>
        <div class="subtitle">Generado: {fecha} · Los precios marcados como "estimados" son 4× el costo importado sin datos reales de MeLi.</div>
    </div>
    <div class="grid">
        {cards}
    </div>
</body>
</html>"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return html_path


# ============================================================
# GENERAR REPORTE
# ============================================================
def generar_reporte(resultados):
    fecha = datetime.now().strftime("%Y-%m-%d")
    hora  = datetime.now().strftime("%H:%M")
    resultados.sort(key=lambda x: x["score"], reverse=True)
    viables = [r for r in resultados if r["viable"]]

    txt_path = os.path.join(OUTPUT_DIR, f"oportunidades_{fecha}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("╔══════════════════════════════════════════════════════════════════╗\n")
        f.write("║       REPORTE DE OPORTUNIDADES DE IMPORTACIÓN                   ║\n")
        f.write("╚══════════════════════════════════════════════════════════════════╝\n")
        f.write(f"Fecha: {fecha} {hora} | Cambio: 1 USD = {TASA_USD_ARS} ARS\n")
        f.write(f"Evaluados: {len(resultados)} | Viables: {len(viables)}\n")
        f.write(f"Filtros: ≥{MIN_SALES_30D} ventas/30d, ratio≥{MIN_RATIO_VENTA}, USD {MIN_PRECIO_USD}-{MAX_PRECIO_USD}\n")

        if MELI_TRENDING:
            f.write(f"MeLi Trending: {', '.join(MELI_TRENDING[:8])}\n")

        f.write("=" * 70 + "\n\n")

        # ── RECOMENDACIÓN PRINCIPAL ───────────────────────────────────────
        top_viables = [r for r in resultados if r["viable"] and "BLOQUEADO" not in r.get("restriccion_nivel","")]
        if top_viables:
            mejor = top_viables[0]
            f.write("🏆 RECOMENDACIÓN — PRODUCTO PARA TESTEAR PRIMERO\n")
            f.write("-" * 70 + "\n")
            f.write(f"  → {mejor['nombre']}\n\n")
            f.write(f"  POR QUÉ ES EL MEJOR:\n")
            f.write(f"  • Score {mejor['score']}/100 — el más alto entre los viables\n")
            f.write(f"  • {mejor['ventas_30d']:,} ventas en 30 días en TikTok Shop USA\n")
            f.write(f"  • Costo importado: USD {mejor['costo_total_usd']} → vendés a ~ARS {mejor['precio_prom_ars']:,}\n")
            f.write(f"  • Multiplicador: {mejor['multiplicador']}x (necesitás ≥{MULTIPLICADOR_MINIMO}x)\n")
            if mejor.get("_trending_match"):
                f.write(f"  • ✅ Aparece en trending MeLi Argentina: \"{mejor['_trending_match']}\"\n")
            f.write(f"  • Estado regulatorio: {mejor['restriccion_nivel']}\n")
            f.write(f"\n  PRÓXIMOS PASOS:\n")
            f.write(f"  1. Buscar en Alibaba: \"{' '.join(mejor['nombre'].split()[:4])}\"\n")
            f.write(f"  2. Pedir muestra (1-3 uds) antes de hacer lote\n")
            f.write(f"  3. Verificar calidad → hacer lote inicial (20-30 uds)\n")
            f.write(f"  4. Publicar en MeLi (ver preview_meli.html para el borrador)\n")
            f.write("=" * 70 + "\n\n")
        else:
            f.write("⚠ No se encontraron productos viables sin restricciones regulatorias.\n")
            f.write("  Revisá los filtros o considerá productos con restricción MODERADO.\n\n")

        # ── RANKING COMPLETO ──────────────────────────────────────────────
        f.write("RANKING COMPLETO\n")
        f.write("=" * 70 + "\n\n")

        for i, p in enumerate(resultados[:15], 1):
            estado = "✅ VIABLE" if p["viable"] else "❌ No viable"
            fuente_tag = f" [{p.get('fuente','?')}]"
            vest_tag   = " ⚠ ventas estimadas" if p.get("ventas_estimadas") else ""
            f.write(f"{i}. {p['nombre']}\n")
            f.write(f"   Fuente: {p.get('fuente','?')}{vest_tag}\n")
            f.write(f"   Categoría: {p['categoria']}\n")
            f.write(f"   Score: {p['score']}/100 | {estado}\n")

            # Trending
            if p.get("_trending_match"):
                f.write(f"   📈 TRENDING en MeLi: \"{p['_trending_match']}\"\n")

            f.write(f"   Precio ref. USD {p['precio_usd']} → "
                    f"Alibaba est.: USD {p['costo_alibaba_usd']}\n")
            if p.get("ventas_estimadas"):
                f.write(f"   Ventas 30d: (estimado — dato de Amazon no disponible)\n")
            else:
                f.write(f"   Influencers: {p['influencers']:,} | "
                        f"Ventas 30d: {p['ventas_30d']:,} | "
                        f"Ventas 7d: {p['ventas_7d']:,} | "
                        f"Ratio: {p['ratio_efic']}\n")
                f.write(f"   Lives: {p['lives_sales']:,} ventas | "
                        f"Videos: {p['videos_sales']:,} ventas\n")
            f.write(f"   Rating: {p['rating']} ⭐ ({p['n_reviews']:,} reseñas)\n")
            f.write(f"   Competencia MeLi: {p['nivel_competencia']} "
                    f"({p['competidores_meli']:,} resultados)\n")
            if p["precio_prom_usd"] > 0:
                tag = " [ESTIMADO]" if p.get("precio_estimado") else ""
                f.write(f"   Precio venta{tag}: USD {p['precio_prom_usd']} "
                        f"(ARS {p['precio_prom_ars']:,})\n")
            f.write(f"   Búsqueda MeLi: \"{p.get('query_meli','')}\"\n")
            f.write(f"   Costo total en Argentina: USD {p['costo_total_usd']}\n")
            f.write(f"   Margen neto: USD {p['margen_neto_usd']} ({p['multiplicador']}x)\n")

            # Restricción regulatoria
            nivel_r = p.get("restriccion_nivel", "OK ✅")
            if "BLOQUEADO" in nivel_r or "COMPLEJO" in nivel_r or "MODERADO" in nivel_r:
                f.write(f"   ⚡ REGULATORIO: {nivel_r} — {p.get('restriccion_desc','')}\n")
            else:
                f.write(f"   {nivel_r}\n")

            if p["url"]:
                f.write(f"   URL: {p['url']}\n")
            f.write("\n")

    csv_path = os.path.join(OUTPUT_DIR, f"oportunidades_{fecha}.csv")
    if resultados:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=resultados[0].keys())
            writer.writeheader()
            writer.writerows(resultados)

    return txt_path, csv_path


# ============================================================
# MAIN
# ============================================================
def main():
    print("\n🔍 EVALUADOR DE PRODUCTOS — INICIO")
    print(f"   Fecha:    {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Fuentes:  TikTok Shop ({len(TIKTOK_KEYWORDS_POR_CATEGORIA)} cats) + Amazon Best Sellers ({len(AMAZON_CATEGORIAS)} cats)")
    print(f"   Filtro:   ≥{MIN_SALES_30D} ventas/30d, ratio≥{MIN_RATIO_VENTA}, "
          f"USD {MIN_PRECIO_USD}-{MAX_PRECIO_USD}\n")

    print("0. Autenticando con MercadoLibre...")
    obtener_token_meli()

    print("\n0b. Obteniendo búsquedas trending en MeLi Argentina...")
    obtener_trending_meli()

    print("\n0c. Tipo de cambio dólar blue...")
    tasa_usd_early = obtener_tasa_dolar()

    # PENDIENTE 1a: TikTok Shop — requiere Apify (límite mensual excedido).
    # Alternativa: Apify plan pago o esperar reset mensual.
    # raw_tiktok = get_tiktok_products()
    raw_tiktok = []
    print(f"\n1a. TikTok Shop — ⏸ PENDIENTE (Apify límite mensual excedido; reactivar con plan pago o al reset)")

    print(f"\n1b. Amazon Movers & Shakers — {len(AMAZON_CATEGORIAS)} categorías (lo que está subiendo ahora)...")
    raw_amazon = get_amazon_movers()
    print(f"    ✅ {len(raw_amazon)} productos de Amazon M&S")

    print(f"\n1c. Precios China — AliExpress ({len(ALIEXPRESS_CATEGORIAS)} cats) + Banggood...")
    raw_aliexpress = get_aliexpress_trending()
    raw_banggood   = get_banggood_trending()
    raw_aliexpress = raw_aliexpress + raw_banggood
    print(f"    ✅ {len(raw_aliexpress)} productos con precio real de importación")

    print(f"\n1d. Influencers IG — {len(INFLUENCER_SOURCES)} cuentas (picks curados por humanos)...")
    raw_influencers = get_influencer_picks()
    _ig_con_p = sum(1 for p in raw_influencers if p.get("_tiene_precio_real"))
    print(f"    ✅ {len(raw_influencers)} productos de cuentas IG  ({_ig_con_p} con precio real, {len(raw_influencers)-_ig_con_p} sin precio)")
    for p in raw_influencers[:5]:
        precio_tag = f"${p.get('_precio_real_usd', 0):.2f}" if p.get("_tiene_precio_real") else "sin precio"
        print(f"       • {p.get('product_title','')[:55]}  [{precio_tag}]")

    print(f"\n1e. NuvoFinds — blog de productos virales curados ({len(NUVOFINDS_SOURCES)} fuentes)...")
    raw_nuvofinds = get_nuvofinds_products()
    _nv_con_p = sum(1 for p in raw_nuvofinds if p.get("_tiene_precio_real"))
    print(f"    ✅ {len(raw_nuvofinds)} productos de NuvoFinds  ({_nv_con_p} con precio real, {len(raw_nuvofinds)-_nv_con_p} sin precio)")
    for p in raw_nuvofinds[:5]:
        dias = p.get("_dias_antiguedad", "?")
        precio_tag = f"${p.get('_precio_real_usd', 0):.2f}" if p.get("_tiene_precio_real") else "sin precio"
        print(f"       • {p.get('product_title','')[:50]}  ({dias}d)  [{precio_tag}]")

    print(f"\n1f. MeLi Argentina — productos de búsquedas trending (scraping directo)...")
    raw_meli_local = get_meli_trending_productos(tasa_usd_early)
    _ml_con_p = sum(1 for p in raw_meli_local if p.get("_tiene_precio_real"))
    print(f"    ✅ {len(raw_meli_local)} productos de MeLi  ({_ml_con_p} con precio en ARS)")
    if raw_meli_local:
        print(f"\n{'─'*100}")
        print(f"  📊 MERCADOLIBRE ARGENTINA — 100 productos trending con precios")
        print(f"  {'#':>3}  {'Keyword':<22}  {'Producto':<48}  {'ARS':>10}  {'USD':>7}")
        print(f"  {'─'*3}  {'─'*22}  {'─'*48}  {'─'*10}  {'─'*7}")
        for i, p in enumerate(raw_meli_local[:100], 1):
            ars = f"${p.get('_precio_ars',0):,.0f}" if p.get('_precio_ars') else "—"
            usd = f"${p.get('_precio_real_usd',0):.1f}" if p.get('_tiene_precio_real') else "—"
            kw  = p.get("_trending_keyword", "")[:22]
            print(f"  {i:3d}. {kw:<22}  {p['product_title'][:48]:<48}  {ars:>10}  {usd:>7}")
        print(f"{'─'*100}")

    raw = raw_tiktok + raw_amazon + raw_aliexpress + raw_influencers + raw_nuvofinds
    if not raw:
        print("   ❌ Sin datos de ninguna fuente.")
        return
    print(f"\n   📦 Total candidatos combinados: {len(raw)}")

    print("\n2. Filtrando por demanda orgánica, precio y restricciones...")
    filtrados = filtrar_productos(raw)
    print(f"   ✅ {len(filtrados)} productos pasan el filtro")

    bloqueados = sum(1 for p in filtrados if "BLOQUEADO" in p.get("restriccion_nivel",""))
    if bloqueados:
        print(f"   ⚠ {bloqueados} tienen restricción BLOQUEADO (penalizados en score)")

    if not filtrados:
        print(f"   Ajustá MIN_SALES_30D (actual: {MIN_SALES_30D}) o "
              f"MIN_RATIO_VENTA (actual: {MIN_RATIO_VENTA})")
        return

    print("\n3. Tipo de cambio dólar blue (ya obtenido)...")
    tasa_usd = tasa_usd_early

    if not MELI_ACCESS_TOKEN:
        print("\n  ⚠ Sin token de MercadoLibre — precios serán ESTIMADOS")

    print("\n4. Evaluando márgenes y calculando score final...")
    # Balancear fuentes: tomar los mejores de cada fuente para no sesgar hacia una sola
    def _balancear(filtrados, tope_total=50):
        fuentes = {}
        for p in filtrados:
            f = p.get("fuente", "?")
            fuentes.setdefault(f, []).append(p)
        resultado = []
        visto = set()
        # Round-robin entre fuentes
        max_ronda = tope_total
        while len(resultado) < tope_total and max_ronda > 0:
            max_ronda -= 1
            agregado = False
            for f in list(fuentes.keys()):
                if fuentes[f] and len(resultado) < tope_total:
                    p = fuentes[f].pop(0)
                    pid = p.get("nombre","")[:30]
                    if pid not in visto:
                        visto.add(pid)
                        resultado.append(p)
                        agregado = True
            if not agregado:
                break
        return resultado

    seleccionados = _balancear(filtrados, tope_total=len(filtrados))
    tope = len(seleccionados)

    # Resumen de fuentes seleccionadas
    from collections import Counter
    dist = Counter(p.get("fuente","?") for p in seleccionados)
    print(f"   Fuentes en evaluación: {dict(dist)}")

    resultados = []
    for i, p in enumerate(seleccionados, 1):
        print(f"   [{i:02d}/{tope}] [{p.get('fuente','?')}] {p['nombre'][:50]}")
        resultados.append(evaluar_producto(p, tasa_usd))

    print("\n5. Generando reporte y preview HTML...")
    txt_path, csv_path = generar_reporte(resultados)

    top5 = sorted(resultados, key=lambda x: x["score"], reverse=True)[:5]
    html_path = generar_preview_html(top5)

    viables = sum(1 for r in resultados if r["viable"])
    con_precio    = sorted([r for r in resultados if r.get("_tiene_precio_real")],
                           key=lambda x: x["score"], reverse=True)
    sin_precio    = sorted([r for r in resultados if not r.get("_tiene_precio_real")],
                           key=lambda x: x["score"], reverse=True)

    print(f"\n✅ LISTO — {viables}/{tope} evaluados | {len(con_precio)} con precio real | {len(sin_precio)} sin precio")

    if con_precio:
        print("\n🏆 TOP 20 PARA IMPORTAR (con precio real):")
        print(f"   {'#':>2}  {'Fuente':<18}  {'Producto':<42}  {'Score':>5}  {'Multi':>5}  {'USD':>6}  {'Ventas/30d':>10}  Competencia")
        print(f"   {'─'*2}  {'─'*18}  {'─'*42}  {'─'*5}  {'─'*5}  {'─'*6}  {'─'*10}  {'─'*10}")
        for i, r in enumerate(con_precio[:20], 1):
            trending_tag = " 📈" if r.get('_trending_match') else ""
            rest_tag     = " ⚠" if "COMPLEJO" in r.get('restriccion_nivel','') else ""
            rest_tag    += " 🚫" if "BLOQUEADO" in r.get('restriccion_nivel','') else ""
            print(f"   {i:2d}. {r.get('fuente','?')[:18]:<18}  {r['nombre'][:42]:<42}  "
                  f"{r['score']:>5}  {r['multiplicador']:>5.1f}x  {r['precio_usd']:>5.0f}$  "
                  f"{r['ventas_30d']:>10,}  {r['nivel_competencia']}{trending_tag}{rest_tag}")

    if sin_precio:
        print(f"\n📋 SIN PRECIO REAL — investigar manualmente ({len(sin_precio)} productos):")
        for i, r in enumerate(sin_precio[:10], 1):
            print(f"   {i:2d}. [{r.get('fuente','?')[:15]}] {r['nombre'][:55]}")

    print(f"\n   📄 Reporte:  {txt_path}")
    print(f"   📊 CSV:      {csv_path}")
    print(f"   🌐 Preview:  {html_path}   ← Abrí este archivo en el navegador\n")


if __name__ == "__main__":
    main()
