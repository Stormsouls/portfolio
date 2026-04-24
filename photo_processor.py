"""
Photo Processor — lado Claude
Aplica el tratamiento cinematográfico usando la máscara generada por SAM.
Claude llama a este script después de que SAM entrega la máscara.

USO (Claude lo llama internamente):
    python photo_processor.py --image foto.jpg --mask sam_mask.png --output resultado.jpg
"""

import argparse
import numpy as np
from PIL import Image, ImageFilter
from pathlib import Path

def cinematic_base(arr, gold_desat=0.85, rest_desat=0.28, gold_hue_min=25, gold_hue_max=68):
    """
    Desaturación selectiva por hue usando luminancia perceptual.
    - gold_desat: factor para tonos dorados (Helena). 1.0 = original, >1 = boost
    - rest_desat: factor para todo lo demás. 0 = B&W, 1 = original
    """
    from colorsys import rgb_to_hls
    a = arr.copy().astype(np.float32)
    a[:,:,0] *= 0.95
    a[:,:,2] *= 1.02
    a *= (2 ** -0.18)
    a = np.where(a > 218, 218 + (a - 218) * 0.4, a)
    a = np.clip(a, 14, 255)
    a_n = np.clip(a / 255.0, 0, 1)

    r, g, b = a_n[:,:,0], a_n[:,:,1], a_n[:,:,2]
    # Perceptual luminance como base gris
    lum = 0.299*r + 0.587*g + 0.114*b

    h_img, w_img = a_n.shape[:2]
    result = np.zeros_like(a_n)
    for y in range(h_img):
        for x in range(w_img):
            rv, gv, bv = float(a_n[y,x,0]), float(a_n[y,x,1]), float(a_n[y,x,2])
            hh, ll, ss = rgb_to_hls(rv, gv, bv)
            hd = hh * 360
            gray = float(lum[y, x])
            factor = gold_desat if gold_hue_min <= hd <= gold_hue_max else rest_desat
            result[y,x,0] = gray + (rv - gray) * factor
            result[y,x,1] = gray + (gv - gray) * factor
            result[y,x,2] = gray + (bv - gray) * factor

    return np.clip(result, 0, 1)

def gold_color_mask(arr_n, hue_min=25, hue_max=68, sat_min=0.30):
    """
    Máscara de lo que ya es dorado en la imagen — el color de Helena.
    Solo pixels que naturalmente tienen ese tono sobreviven al gris.
    """
    from colorsys import rgb_to_hls
    h, w = arr_n.shape[:2]
    mask = np.zeros((h, w), dtype=np.float32)
    for y in range(h):
        for x in range(w):
            rv, gv, bv = float(arr_n[y,x,0]), float(arr_n[y,x,1]), float(arr_n[y,x,2])
            hh, ll, ss = rgb_to_hls(rv, gv, bv)
            hd = hh * 360
            if hue_min <= hd <= hue_max and ss >= sat_min and 0.20 < ll < 0.88:
                # Weight by saturation strength — más dorado = más vivo
                mask[y, x] = min(1.0, (ss - sat_min) / 0.4)
    return mask

def apply_selective_color(arr_orig_n, arr_cine, sam_mask_n, sat_boost=2.7):
    """
    SAM mask define la zona artísticamente relevante (excluye edificios, fondos).
    Dentro de esa zona, solo lo que ya es dorado (Helena) sobrevive al gris.
    """
    from PIL import Image as PILImage, ImageFilter as PILFilter

    # Gold pixels en toda la imagen
    gold_mask = gold_color_mask(arr_orig_n)

    # Combinar: gold AND dentro de la zona SAM
    combined = gold_mask * sam_mask_n

    # Suavizar bordes
    combined_img = PILImage.fromarray((np.clip(combined, 0, 1) * 255).astype(np.uint8))
    combined_smooth = np.array(combined_img.filter(PILFilter.GaussianBlur(5)), dtype=np.float32) / 255.0
    combined_smooth = np.clip(combined_smooth, 0, 1)

    # Versión vívida del original (solo amplifica lo que ya existe)
    r, g, b = arr_orig_n[:,:,0], arr_orig_n[:,:,1], arr_orig_n[:,:,2]
    lum = 0.299*r + 0.587*g + 0.114*b
    vivid = np.stack([
        np.clip(lum + (r - lum) * sat_boost, 0, 1),
        np.clip(lum + (g - lum) * sat_boost, 0, 1),
        np.clip(lum + (b - lum) * sat_boost, 0, 1)
    ], axis=2)

    m = combined_smooth[:,:, np.newaxis]
    return np.clip(arr_cine * (1 - m) + vivid * m, 0, 1)

def add_grain_vignette(arr):
    h, w = arr.shape[:2]
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt(((X - w/2)/(w/2))**2 + ((Y - h/2)/(h/2))**2)
    arr = arr * (1 - np.clip(dist * 0.36, 0, 0.26))[:,:, np.newaxis]
    np.random.seed(42)
    arr += np.random.normal(0, 0.015, arr.shape)
    return np.clip(arr, 0, 1)

def process(image_path, mask_path, output_path, desat=0.45, sat_boost=2.7):
    img = Image.open(image_path).convert("RGB")
    arr = np.array(img, dtype=np.float32)
    arr_n = arr / 255.0

    # Load SAM mask
    mask_img = Image.open(mask_path).convert("L")
    mask_img = mask_img.resize((img.width, img.height), Image.LANCZOS)
    mask_raw = np.array(mask_img, dtype=np.float32) / 255.0
    # Smooth mask edges
    mask_smooth = np.array(
        Image.fromarray((mask_raw * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(4)),
        dtype=np.float32
    ) / 255.0

    arr_cine = cinematic_base(arr, gold_desat=1.1, rest_desat=desat)
    result = apply_selective_color(arr_n, arr_cine, mask_smooth, sat_boost=sat_boost)
    result = add_grain_vignette(result)

    Image.fromarray((result * 255).astype(np.uint8)).save(output_path, "JPEG", quality=95)
    print(f"Guardado: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--mask", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--desat", type=float, default=0.45)
    parser.add_argument("--sat-boost", type=float, default=2.7)
    args = parser.parse_args()
    process(args.image, args.mask, args.output, args.desat, args.sat_boost)
