import cv2
from python.ml.image_classification.initial_prediction import init_pred

cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break
    results = init_pred(frame)

    #cv2.imshow("YOLO Webcam Detection", frame)