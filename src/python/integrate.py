import time
import serial
from python.ml.irrigation_system.init_pred import predict
# Replace 'COM3' with your actual port (e.g., '/dev/ttyACM0' on Mac/Linux)
arduino = serial.Serial(port='/dev/ttyUSB0', baudrate=9600, timeout=1)
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
            print(f"predict {predict(adc_value, 20, 67)}")

except KeyboardInterrupt:
    print("Closing connection...")
    arduino.close()
