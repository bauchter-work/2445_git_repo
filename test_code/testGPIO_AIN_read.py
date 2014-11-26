import Adafruit_BBIO.GPIO as GPIO
import Adafruit_BBIO.ADC as ADC

ADC.setup()
Value = ADC.read("P9_36") #Returns a value from 0 to 1
Voltage = Value*1.8       #converts to a voltage value

print "Voltage is: ",Voltage," volts"

