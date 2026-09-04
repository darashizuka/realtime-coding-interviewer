# modules/attention_detector.py
"""Attention (focused / distracted) classifier used by the interview server.

This module is deliberately framework-free: it has to be importable from the
Socket.IO backend without dragging in any UI dependencies.
"""
import os

import torch
import torch.nn as nn
from torchvision import models, transforms

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(MODULE_DIR)
DEFAULT_CHECKPOINT = os.path.join(
    REPO_ROOT, "detection_models", "attention_model_pretrained.pth"
)

# Class index -> meaning, matching modules/attention_detection_training.ipynb
CLASS_DISTRACTED = 0
CLASS_FOCUSED = 1

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

_model = None
_device = None


def load_model(checkpoint_path=DEFAULT_CHECKPOINT):
    """Load the ResNet18 attention classifier, caching after the first call.

    Raises FileNotFoundError when the checkpoint is missing. The previous
    version swallowed that and fell back to random weights, which left the
    distraction feature looking alive while emitting pure noise.
    """
    global _model, _device
    if _model is not None:
        return _model, _device

    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(
            f"Attention checkpoint not found at {checkpoint_path}. "
            "Expected detection_models/attention_model_pretrained.pth."
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, 2)
    model.load_state_dict(torch.load(checkpoint_path, map_location=device))
    model.eval()
    model.to(device)

    _model, _device = model, device
    return model, device


def predict_is_distracted(pil_image, model, device):
    """Return True when the frame is classified as distracted.

    Synchronous and CPU/GPU bound - callers on an event loop should run this in
    an executor.
    """
    input_tensor = transform(pil_image).unsqueeze(0).to(device)
    with torch.no_grad():
        output = model(input_tensor)
        _, pred = torch.max(output, 1)
    return pred.item() == CLASS_DISTRACTED
