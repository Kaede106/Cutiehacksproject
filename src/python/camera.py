import cv2
from python.ml.image_classification.initial_prediction import init_pred

cap = cv2.VideoCapture(0)

def cam():
    ret, frame = cap.read()
    if not ret:
        return 1
    results = init_pred(frame)
    print(results)
    if len(results)==0:
        return 1
    s = results[0][0]
    return 0 if s < 260 else 2 if s > 340 else 1
while True:
    print(cam())