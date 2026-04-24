# Import Intelligence Bot 🇨🇳→🇦🇷

Sistema automatizado de inteligencia de mercado para detectar productos trending en EE.UU. y evaluar su viabilidad de importación desde China hacia Argentina. Monitorea en tiempo real TikTok Shop, Amazon Movers & Shakers, blogs curados e influencers de Instagram para identificar productos con demanda validada antes de invertir capital. Cruza esas señales con un modelo de costos completo (precio Alibaba + flete aéreo + IVA aduana 21% + derechos + comisión MercadoLibre) y calcula el margen neto y multiplicador de cada oportunidad. El publicador interactivo permite listar los productos ganadores directamente en MercadoLibre Argentina con precios calculados automáticamente.

---

## Features

- **Multi-source trend detection** — TikTok Shop vía Apify, Amazon Movers & Shakers (12 categorías, productos subiendo más rápido en 24h), páginas link-in-bio de influencers IG (beacons.ai / Linktree), y blogs curados de productos virales (NuvoFinds, KydsChoice, Shopify blogs)
- **Real price extraction** — extrae precios reales de páginas de producto Amazon (US/DE/UK), tiendas Shopify vía API nativa, y sigue cadenas de redirect de links de afiliados (rstyle.me, amzn.to, go.magik.ly, etc.)
- **Import cost model** — precio Alibaba estimado como 33% del precio TikTok USA (o precio real AliExpress si disponible), + flete aéreo $4/u, + IVA aduana 21%, + derechos 5%, + comisión MeLi 15% → multiplicador y margen neto en USD
- **Scoring 0–100** — demanda (35pts) + eficiencia de ventas (15pts) + calidad/reviews (10pts) + competencia MeLi (15pts) + margen (15pts) + bonuses trending y novedad
- **MercadoLibre Argentina integration** — OAuth 2.0 Authorization Code con auto-refresh de token, scraping de keywords trending de MeLi, y publicación directa vía API (POST /items)
- **Regulatory compliance** — alertas automáticas ANMAT / SENASA / ENACOM para categorías restringidas (cosméticos, alimentos, electrónica, juguetes, etc.) con penalización en score
- **Dollar blue tracking** — tipo de cambio informal con múltiples fuentes de fallback y caché de 7 días
- **Interactive publisher** — lee el CSV del evaluador, muestra cada producto viable con precio sugerido en ARS, permite confirmar o ajustar, y publica en MeLi
- **Anti-bot / Cloudflare bypass** — Playwright headless con stealth (navigator.webdriver=undefined) para sitios protegidos
- **Windows-native** — launchers .bat para ejecución con doble click, sin tocar la terminal

---

## Stack

| Componente | Tecnología |
|---|---|
| Web scraping | `requests`, `BeautifulSoup4`, `Playwright` (Chromium headless) |
| Auth | MercadoLibre OAuth 2.0 Authorization Code Flow |
| Trend data | Apify (TikTok Shop), Amazon M&S HTML, beacons.ai, Blogger/Shopify JSON |
| Outputs | CSV, TXT, HTML preview |
| Runtime | Python 3.10+, Windows |

---

## Setup

### 1. Clonar y dependencias

```bash
git clone https://github.com/TU_USUARIO/import-intelligence-bot.git
cd import-intelligence-bot
pip install requests beautifulsoup4 playwright
playwright install chromium
```

### 2. Credenciales

Copiar `.env.example` a `.env` y completar:

```bash
cp .env.example .env
```

- **MercadoLibre App**: crear app en [developers.mercadolibre.com.ar](https://developers.mercadolibre.com.ar/), usar `https://httpbin.org/get` como Redirect URI
- **Apify**: token en [console.apify.com/account/integrations](https://console.apify.com/account/integrations)

### 3. Token MeLi (una sola vez)

```bash
python setup_meli_token.py
```

---

## Uso

```bash
# Evaluar oportunidades (correr 1x/semana)
python evaluador_productos.py

# Publicar en MeLi (solo cuando tenés stock físico)
python publicador_meli.py
```

O usar los launchers `.bat` en Windows con doble click.

---

## Outputs

| Archivo | Contenido |
|---|---|
| `oportunidades_YYYY-MM-DD.csv` | Todos los productos evaluados con scores y márgenes |
| `oportunidades_YYYY-MM-DD.txt` | Reporte legible con top oportunidades y próximos pasos |
| `preview_meli_YYYY-MM-DD.html` | Vista previa HTML estilo MercadoLibre |
| `publicaciones_meli.csv` | Log de publicaciones realizadas |

---

## Arquitectura

```
evaluador_productos.py
├── Fuentes de trending
│   ├── get_tiktok_products()      # Apify actor
│   ├── get_amazon_movers()        # HTML scraping + price extraction
│   ├── get_aliexpress_trending()  # glosearch API + Playwright fallback
│   ├── get_banggood_trending()    # Playwright multi-step (bypass geo-selector)
│   ├── get_influencer_picks()     # beacons.ai / Linktree + __NEXT_DATA__ parsing
│   └── get_nuvofinds_products()   # Blogger JSON feed + Shopify article API
├── filtrar_productos()            # Demanda, precio, restricciones regulatorias
├── calcular_margen()              # Modelo de costos importación Argentina
├── check_meli()                   # Búsqueda competencia + precio referencia MeLi
├── calcular_score()               # Score 0-100
└── generar_reporte()              # CSV + TXT + HTML preview

publicador_meli.py
├── Lee CSV del evaluador
├── Muestra productos viables interactivamente
└── POST /items → MercadoLibre Argentina
```

---

## Disclaimer

Este proyecto es para uso educativo y de investigación. No incluye credenciales ni datos personales. Los precios y márgenes son estimaciones; verificar siempre antes de invertir capital.
