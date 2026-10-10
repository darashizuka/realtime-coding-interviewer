# modules/attention_detector.py
"""Attention (focused / distracted) classifier used by the interview server.

Uses ONNX Runtime instead of PyTorch for ~80% lower memory footprint.
"""
import os

import numpy as np
import onnxruntime as ort
from PIL import Image

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(MODULE_DIR)
DEFAULT_CHECKPOINT = os.path.join(
    REPO_ROOT, "detection_models", "attention_model_pretrained.onnx"
)

CLASS_DISTRACTED = 0
CLASS_FOCUSED = 1

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)

_session = None


def load_model(checkpoint_path=DEFAULT_CHECKPOINT):
    global _session
    if _session is not None:
        return _session, "onnxruntime"

    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(
            f"Attention checkpoint not found at {checkpoint_path}. "
            "Expected detection_models/attention_model_pretrained.onnx."
        )

    _session = ort.InferenceSession(
        checkpoint_path, providers=["CPUExecutionProvider"]
    )
    return _session, "onnxruntime"


def _preprocess(pil_image: Image.Image) -> np.ndarray:
    img = pil_image.resize((224, 224), Image.BILINEAR)
    arr = np.array(img, dtype=np.float32) / 255.0
    arr = arr.transpose(2, 0, 1)  # HWC -> CHW
    arr = (arr - MEAN) / STD
    return arr[np.newaxis]  # add batch dim


def predict_is_distracted(pil_image, session, _device=None):
    input_tensor = _preprocess(pil_image)
    outputs = session.run(None, {"input": input_tensor})
    pred = int(np.argmax(outputs[0], axis=1)[0])
    return pred == CLASS_DISTRACTED
