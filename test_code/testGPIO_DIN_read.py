import Adafruit_BBIO.GPIO as GPIO
import time

GPIO.setup("P8_16",GPIO.IN)

while True:
    if GPIO.input("P8_16"):
        print("Pin is HIGH")
    else:
        print("Pin is LOW")
    time.sleep(1)
