import cv2
from python.ml.image_classification.initial_prediction import init_pred
from python.ml.irrigation_system.init_pred import predict

cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break
    results = predict(0, 0, 0)
    init_pred(frame)
    annotated_frame = results[0].plot()

    cv2.imshow("YOLO Webcam Detection", annotated_frame)