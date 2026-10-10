"""One-time script: convert the PyTorch ResNet18 checkpoint to ONNX format."""
import torch
import torch.nn as nn
from torchvision import models

SRC = "detection_models/attention_model_pretrained.pth"
DST = "detection_models/attention_model_pretrained.onnx"

model = models.resnet18(weights=None)
model.fc = nn.Linear(model.fc.in_features, 2)
model.load_state_dict(torch.load(SRC, map_location="cpu"))
model.eval()

dummy = torch.randn(1, 3, 224, 224)
torch.onnx.export(
    model,
    dummy,
    DST,
    input_names=["input"],
    output_names=["output"],
    dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
    opset_version=17,
)
print(f"Exported {DST}")
