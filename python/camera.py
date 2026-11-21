import cv2
from ..ml.image_classification import initial_prediction
from ..ml.irrigation_system import init_pred

cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break
    results = predict(0, 0, 0)
    init_pred(frame)
    annotated_frame = results[0].plot()

    cv2.imshow("YOLO Webcam Detection", annotated_frame)