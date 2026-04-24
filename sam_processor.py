"""
SAM Processor — Agencia entropiaconcept
Corre en background en tu máquina. Espera requests de Claude, procesa con SAM, devuelve máscaras.

INSTALACIÓN (una vez):
    pip install mobile-sam
    # Para SAM original (necesita ~8GB RAM):
    pip install segment-anything
    # Descargar pesos:
    # MobileSAM: https://github.com/ChaoningZhang/MobileSAM/blob/master/weights/mobile_sam.pt
    # SAM ViT-H:  wget https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth

CORRER:
    python sam_processor.py
    # O para SAM original:
    python sam_processor.py --model sam --weights /ruta/a/sam_vit_h_4b8939.pth
"""

import json
import time
import os
import sys
import argparse
import numpy as np
from pathlib import Path
from PIL import Image

WATCH_DIR = Path(__file__).parent
REQUEST_FILE = WATCH_DIR / "sam_request.json"
RESULT_FILE = WATCH_DIR / "sam_result.json"
POLL_INTERVAL = 1.5  # segundos

def load_model(model_type="mobile", weights_path=None):
    if model_type == "mobile":
        try:
            from mobile_sam import sam_model_registry, SamPredictor
            default_weights = WATCH_DIR / "mobile_sam.pt"
            weights = weights_path or str(default_weights)
            print(f"[SAM] Cargando MobileSAM desde {weights}...")
            model = sam_model_registry["vit_t"](checkpoint=weights)
            model.eval()
            return SamPredictor(model)
        except ImportError:
            print("[ERROR] MobileSAM no instalado. Corré: pip install mobile-sam")
            sys.exit(1)
    else:
        try:
            from segment_anything import sam_model_registry, SamPredictor
            default_weights = WATCH_DIR / "sam_vit_h_4b8939.pth"
            weights = weights_path or str(default_weights)
            print(f"[SAM] Cargando SAM ViT-H desde {weights}...")
            model = sam_model_registry["vit_h"](checkpoint=weights)
            model.eval()
            return SamPredictor(model)
        except ImportError:
            print("[ERROR] segment-anything no instalado. Corré: pip install segment-anything")
            sys.exit(1)

def process_request(predictor, request):
    """
    request = {
        "image_path": "/ruta/foto.jpg",
        "highlights": [
            {
                "label": "flores",
                "bbox": [x1_norm, y1_norm, x2_norm, y2_norm],  # 0-1 normalized
                "positive_points": [[x_norm, y_norm], ...],
                "negative_points": [[x_norm, y_norm], ...]
            }
        ],
        "output_mask_path": "/ruta/mask.png"
    }
    """
    image = Image.open(request["image_path"]).convert("RGB")
    img_array = np.array(image)
    H, W = img_array.shape[:2]

    predictor.set_image(img_array)

    combined_mask = np.zeros((H, W), dtype=np.uint8)

    for hint in request["highlights"]:
        # Convert normalized coords to pixels
        bbox = hint.get("bbox")
        pos_pts = hint.get("positive_points", [])
        neg_pts = hint.get("negative_points", [])

        input_box = None
        if bbox:
            x1 = int(bbox[0] * W)
            y1 = int(bbox[1] * H)
            x2 = int(bbox[2] * W)
            y2 = int(bbox[3] * H)
            input_box = np.array([x1, y1, x2, y2])

        input_points = None
        input_labels = None
        if pos_pts or neg_pts:
            points = [[int(p[0]*W), int(p[1]*H)] for p in pos_pts] + \
                     [[int(p[0]*W), int(p[1]*H)] for p in neg_pts]
            labels = [1]*len(pos_pts) + [0]*len(neg_pts)
            input_points = np.array(points)
            input_labels = np.array(labels)

        masks, scores, _ = predictor.predict(
            point_coords=input_points,
            point_labels=input_labels,
            box=input_box,
            multimask_output=True
        )

        # Use best scoring mask
        best = masks[np.argmax(scores)]
        combined_mask = np.logical_or(combined_mask, best).astype(np.uint8) * 255

    # Save mask
    out_path = request["output_mask_path"]
    Image.fromarray(combined_mask).save(out_path)
    print(f"[SAM] Máscara guardada: {out_path}")
    return out_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["mobile", "sam"], default="mobile")
    parser.add_argument("--weights", type=str, default=None)
    args = parser.parse_args()

    print(f"[SAM Processor] Iniciando con modelo: {args.model}")
    predictor = load_model(args.model, args.weights)
    print(f"[SAM Processor] Listo. Esperando requests en: {WATCH_DIR}")
    print(f"[SAM Processor] Ctrl+C para detener.\n")

    while True:
        if REQUEST_FILE.exists():
            try:
                with open(REQUEST_FILE) as f:
                    request = json.load(f)

                print(f"[SAM] Procesando: {request.get('image_path', '?')}")
                os.remove(REQUEST_FILE)  # consume el request

                mask_path = process_request(predictor, request)

                with open(RESULT_FILE, "w") as f:
                    json.dump({"status": "ok", "mask_path": mask_path}, f)

            except Exception as e:
                print(f"[SAM ERROR] {e}")
                with open(RESULT_FILE, "w") as f:
                    json.dump({"status": "error", "message": str(e)}, f)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
