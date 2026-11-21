from ultralytics import YOLO

# Load a pretrained model
model = YOLO("yolo26n.pt")

# Run object detection
results = model.predict(
    source="orange.jpg",
    save=True
)

def init_pred(source):
    results = model.predict(
        source=source,       # Default webcam
        stream=True,    # Process frames continuously
        show=True,
        conf=0.5
    )

    output_thing = []
    for result in results:
        for box in result.boxes:
            # Get bounding box coordinates
            x1, y1, x2, y2 = box.xyxy[0].tolist()

            print("Top-left:", (x1, y1))
            print("Bottom-right:", (x2, y2))
            output_thing.append((x1+x2)/2, (y1+y2)/2)  # Append the center coordinates of the bounding box

    return output_thing


    
