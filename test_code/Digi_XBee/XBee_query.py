"""
Continuously read the serial port and process IO data received from a
remote XBee.
"""

from xbee import zigbee
import serial

ser = serial.Serial('/dev/ttyO4', 9600)

xbee = zigbee.ZigBee(ser)

# Continuously read and print packets
while True:
    try:
        response = xbee.wait_read_frame()
        print response
    except KeyboardInterrupt:
        break

ser.close()
