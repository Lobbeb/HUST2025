import serial

# Replace 'COM3' with your ESP32's serial port name
# On Linux or macOS, it might be something like '/dev/ttyUSB0dsadass'
ser = serial.Serial('COM3', 115200)  # Port and baud rate

while True:
    if ser.in_waiting:  # Check if data is available to read
        data = ser.readline().decode('utf-8').strip()
        print(f"Received: {data}")
