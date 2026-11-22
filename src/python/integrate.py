import time
import serial
from python.ml.irrigation_system.init_pred import predict
from python.camera import cam
# Replace 'COM3' with your actual port (e.g., '/dev/ttyACM0' on Mac/Linux)
arduino = serial.Serial(port='COM7', baudrate=9600, timeout=1)
time.sleep(2)  # Wait for Arduino to finish resetting

try:
    print("hello")
    while True:
        # Check if data is waiting in the buffer
        if arduino.in_waiting > 0:
            # Read the line, convert bytes to string, and remove \r\n
            line = arduino.readline().decode('utf-8').rstrip()
            try:
                adc_value = int(line)
            except ValueError:
                print(f"Invalid serial data: {line}")
                continue
            print(f"Received from Arduino: {line}")
            prediction = predict(adc_value, 20, 67)
            print(f"predict {prediction}")

            motor_position = cam()  # 0 = left, 1 = middle, 2 = right

            arduino.write(f"{prediction}|{motor_position}\n".encode("utf-8"))
            #arduino.write(f"M:".encode("utf-8"))

except KeyboardInterrupt:
    print("Closing connection...")
finally:
    arduino.close()
