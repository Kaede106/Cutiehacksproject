import time
import serial
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
            print(f"Received from Arduino: {line}")

except KeyboardInterrupt:
    print("Closing connection...")
    arduino.close()
