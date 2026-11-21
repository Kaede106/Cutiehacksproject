from ultralytics import YOLO

# Load a pretrained model
model = YOLO("yolo26n.pt")

# Run object detection
results = model.predict(
    source="orange.jpg",
    save=True
)

# TRANSFER LEARNING

# 