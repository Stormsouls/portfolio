"""
Auto Processor — entropiaconcept
Corre en background. Detecta fotos nuevas, aplica SAM automático + tratamiento
cinematográfico con gold selective color (Helena = Citrinitas).

INSTALACIÓN:
    pip install mobile-sam timm torch torchvision Pillow numpy

CORRER:
    python auto_processor.py

Deja esto corriendo. Cada foto nueva que tirés a la carpeta aparece procesada
como [nombre]_editado.jpeg en ~30-60 segundos.

Para copy + hashtags: abrí el chat con Claude y pedíselo.
"""

import time
import os
import sys
import numpy as np
from pathlib import Path
from PIL import Image, ImageFilter
from colorsys import rgb_to_hls

# ── Config ──────────────────────────────────────────────────────────────────
WATCH_DIR    = Path(__file__).parent
POLL_SEC     = 3
SUFFIX       = "_editado"
EXTENSIONS   = {".jpg", ".jpeg", ".png"}
WEIGHTS_PATH = WATCH_DIR / "mobile_sam.pt"

# Visual params
GOLD_HUE_MIN  = 25    # rango dorado (Helena)
GOLD_HUE_MAX  = 68
REST_DESAT    = 0.28  # desaturación del resto (no B&W, con atmósfera)
GOLD_DESAT    = 1.1   # base dorada (levemente sobre original)
GOLD_SAT_BOOST = 1.8  # boost final sobre la zona dorada

# SAM auto mask selection
MIN_MASK_AREA_RATIO = 0.03   # mínimo 3% de la imagen
MAX_MASK_AREA_RATIO = 0.80   # máximo 80% (evita fondo completo)
MIN_SCORE           = 0.88   # confianza mínima de SAM

# ── Load SAM ────────────────────────────────────────────────────────────────
def load_sam():
    try:
        from mobile_sam import sam_model_registry, SamAutomaticMaskGenerator
        print(f"[Auto] Cargando MobileSAM desde {WEIGHTS_PATH}...")
        model = sam_model_registry["vit_t"](checkpoint=str(WEIGHTS_PATH))
        model.eval()
        mask_gen = SamAutomaticMaskGenerator(
            model,
            points_per_side=16,
            pred_iou_thresh=MIN_SCORE,
            stability_score_thresh=0.88,
            min_mask_region_area=500,
        )
        print("[Auto] MobileSAM listo.\n")
        return mask_gen
    except Exception as e:
        print(f"[ERROR] No se pudo cargar SAM: {e}")
        print("        Procesará sin SAM (gold filter global).")
        return None

# ── Cinematic base ───────────────────────────────────────────────────────────
def cinematic_base(arr):
    a = arr.copy().astype(np.float32)
    a[:,:,0] *= 0.95
    a[:,:,2] *= 1.02
    a *= (2 ** -0.18)
    a = np.where(a > 218, 218 + (a - 218) * 0.4, a)
    a = np.clip(a, 14, 255)
    a_n = np.clip(a / 255.0, 0, 1)

    r, g, b  = a_n[:,:,0], a_n[:,:,1], a_n[:,:,2]
    lum      = 0.299*r + 0.587*g + 0.114*b
    h_img, w_img = a_n.shape[:2]
    result   = np.zeros_like(a_n)

    for y in range(h_img):
        for x in range(w_img):
            rv, gv, bv = float(a_n[y,x,0]), float(a_n[y,x,1]), float(a_n[y,x,2])
            hh, ll, ss = rgb_to_hls(rv, gv, bv)
            hd         = hh * 360
            gray       = float(lum[y, x])
            factor     = GOLD_DESAT if GOLD_HUE_MIN <= hd <= GOLD_HUE_MAX else REST_DESAT
            result[y,x,0] = gray + (rv - gray) * factor
            result[y,x,1] = gray + (gv - gray) * factor
            result[y,x,2] = gray + (bv - gray) * factor

    return np.clip(result, 0, 1)

# ── Gold mask ────────────────────────────────────────────────────────────────
def gold_mask(arr_n, sam_mask_n):
    """Pixels dorados dentro de la zona SAM."""
    h, w = arr_n.shape[:2]
    mask = np.zeros((h, w), dtype=np.float32)
    for y in range(h):
        for x in range(w):
            if sam_mask_n[y, x] < 0.1:
                continue
            rv, gv, bv = float(arr_n[y,x,0]), float(arr_n[y,x,1]), float(arr_n[y,x,2])
            hh, ll, ss = rgb_to_hls(rv, gv, bv)
            hd = hh * 360
            if GOLD_HUE_MIN <= hd <= GOLD_HUE_MAX and ss >= 0.28 and 0.20 < ll < 0.88:
                mask[y, x] = min(1.0, (ss - 0.28) / 0.35)
    # Smooth
    mask_img = Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8))
    mask_s   = np.array(mask_img.filter(ImageFilter.GaussianBlur(5)), dtype=np.float32) / 255.0
    return np.clip(mask_s, 0, 1)

# ── Apply selective color ─────────────────────────────────────────────────────
def apply_selective(arr_n, arr_cine, mask):
    r, g, b = arr_n[:,:,0], arr_n[:,:,1], arr_n[:,:,2]
    lum     = 0.299*r + 0.587*g + 0.114*b
    f       = GOLD_SAT_BOOST
    vivid   = np.stack([np.clip(lum+(r-lum)*f,0,1),
                        np.clip(lum+(g-lum)*f,0,1),
                        np.clip(lum+(b-lum)*f,0,1)], axis=2)
    m = mask[:,:, np.newaxis]
    return np.clip(arr_cine*(1-m) + vivid*m, 0, 1)

# ── Grain + vignette ──────────────────────────────────────────────────────────
def grain_vignette(arr):
    h, w = arr.shape[:2]
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt(((X-w/2)/(w/2))**2 + ((Y-h/2)/(h/2))**2)
    arr  = arr * (1 - np.clip(dist*0.36, 0, 0.26))[:,:, np.newaxis]
    np.random.seed(42)
    arr += np.random.normal(0, 0.015, arr.shape)
    return np.clip(arr, 0, 1)

# ── SAM → best combined mask ──────────────────────────────────────────────────
def get_sam_mask(mask_gen, img_array):
    if mask_gen is None:
        # Sin SAM: zona completa
        h, w = img_array.shape[:2]
        return np.ones((h, w), dtype=np.float32)

    total_px = img_array.shape[0] * img_array.shape[1]
    masks    = mask_gen.generate(img_array)

    # Filtrar por tamaño y score
    good = [m for m in masks
            if MIN_MASK_AREA_RATIO <= m["area"]/total_px <= MAX_MASK_AREA_RATIO
            and m["predicted_iou"] >= MIN_SCORE]

    if not good:
        # Fallback: zona completa
        h, w = img_array.shape[:2]
        return np.ones((h, w), dtype=np.float32)

    # Combinar los mejores (top 5 por score)
    good.sort(key=lambda m: m["predicted_iou"], reverse=True)
    combined = np.zeros(img_array.shape[:2], dtype=np.float32)
    for m in good[:5]:
        combined = np.logical_or(combined, m["segmentation"]).astype(np.float32)

    return combined

# ── Process one image ─────────────────────────────────────────────────────────
def process_image(path, mask_gen):
    print(f"[Auto] Procesando: {path.name}")
    img    = Image.open(path).convert("RGB")
    arr    = np.array(img, dtype=np.float32)
    arr_n  = arr / 255.0

    # SAM mask
    sam_m  = get_sam_mask(mask_gen, arr.astype(np.uint8))

    # Pipeline
    cine   = cinematic_base(arr)
    gmask  = gold_mask(arr_n, sam_m)
    result = apply_selective(arr_n, cine, gmask)
    result = grain_vignette(result)

    out_path = path.parent / f"{path.stem}{SUFFIX}.jpeg"
    Image.fromarray((result*255).astype(np.uint8)).save(out_path, "JPEG", quality=95)
    print(f"[Auto] Listo → {out_path.name}\n")

# ── Watcher loop ──────────────────────────────────────────────────────────────
def is_processed(name):
    stem = Path(name).stem
    return stem.endswith(SUFFIX)

def main():
    mask_gen = load_sam()
    seen     = set(WATCH_DIR.iterdir())  # archivos al arrancar, no los procesamos

    print(f"[Auto] Vigilando: {WATCH_DIR}")
    print(f"[Auto] Tirá cualquier foto a la carpeta para procesarla automáticamente.")
    print(f"[Auto] Ctrl+C para detener.\n")

    while True:
        current = set(WATCH_DIR.iterdir())
        new     = current - seen

        for f in sorted(new):
            if f.suffix.lower() in EXTENSIONS and not is_processed(f.name):
                time.sleep(1)  # esperar que termine de copiarse
                try:
                    process_image(f, mask_gen)
                except Exception as e:
                    print(f"[ERROR] {f.name}: {e}")

        seen = current
        time.sleep(POLL_SEC)

if __name__ == "__main__":
    main()
