#!/usr/bin/python

import time, signal, sys
from Adafruit_ADS1x15 import ADS1x15

def signal_handler(signal, frame):
        print 'You pressed Ctrl+C!'
        sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)
#print 'Press Ctrl+C to exit'

ADS1015 = 0x00  # 12-bit ADC
ADS1115 = 0x01	# 16-bit ADC

# Select the gain
# gain = 61    # +/- 6.144V
gain = 4096  # +/- 4.096V
# gain = 2048  # +/- 2.048V
# gain = 1024  # +/- 1.024V
# gain = 512   # +/- 0.512V
# gain = 256   # +/- 0.256V

# Select the sample rate
# sps = 8    # 8 samples per second
# sps = 16   # 16 samples per second
# sps = 32   # 32 samples per second
# sps = 64   # 64 samples per second
# sps = 128  # 128 samples per second
sps = 250  # 250 samples per second
# sps = 475  # 475 samples per second
# sps = 860  # 860 samples per second

# Initialise the ADCs using the default mode (use default I2C address)
# Set this to ADS1015 or ADS1115 depending on the ADC you are using!
adc1 = ADS1x15(address = 0x48, ic=ADS1115)
adc2 = ADS1x15(address = 0x49, ic=ADS1115)
adc3 = ADS1x15(address = 0x4A, ic=ADS1115)
#adc4 = ADS1x15(address = 0x4B, ic=ADS1115)

# Read ADC1, channel 0 in single-ended mode using the settings above
Value = adc1.readADCSingleEnded(0,gain,sps)
Value = adc1.readADCSingleEnded(0,gain,sps)
Voltage = Value / 1000
print "ADC1, Channel 1, reads: %.6f volts" % (Voltage)

# Read ADC2, channel 0 in single-ended mode using the same settings
Value = adc2.readADCSingleEnded(0,gain,sps)
Value = adc2.readADCSingleEnded(0,gain,sps)
Voltage = Value / 1000
print "ADC2, Channel 1, reads: %.6f volts" % (Voltage)

# Read ADC3, channel 0 in single-ended mode using the same settings
Value = adc3.readADCSingleEnded(0,gain,sps)
Value = adc3.readADCSingleEnded(0,gain,sps)
Voltage = Value / 1000
print "ADC3, Channel 1, reads: %.6f volts" % (Voltage)

# Read ADC4, channel 0 in single-ended mode using the same settings
#Value = adc4.readADCSingleEnded(0,gain,sps)
#Value = adc4.readADCSingleEnded(0,gain,sps)
#Voltage = Value / 1000
#print "ADC4, Channel 1, reads: %.6f volts" % (Voltage)

# To read channel  in single-ended mode, +/- 1.024V, 860 sps use:
# volts = adc.readADCSingleEnded(3, 1024, 860)

#print "%.6f" % (volts)
