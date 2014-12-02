import Adafruit_BBIO.GPIO as GPIO
import time

#no conflict pins:
#P8_7, P8_8, P8_9, P8_10, P8_11, P8_12, P8_13, P8_14

#pins = ["P8_7","P8_8","P8_9","P8_10","P8_11","P8_12","P8_13","P8_14"]
pins = ["P8_15"]

for x in pins:
	GPIO.setup(x, GPIO.OUT)

for x in pins:
  print "setting output high ", x
  GPIO.output(x, GPIO.HIGH)

while (True):
    time.sleep(5)

GPIO.cleanup()  #Sets all configured pins in this program back to being inputs.
print "Exit"

