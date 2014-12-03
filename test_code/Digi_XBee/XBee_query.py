"""
Continuously read the serial port and process IO data received from a
remote XBee.
"""

from xbee import zigbee
import serial
import Adafruit_BBIO.UART as UART

UART.setup("UART4")
ser = serial.Serial('/dev/ttyO4', 9600)

xbee = zigbee.ZigBee(ser)

print "Xbee serial port open:"

# Continuously read and print packets
while True:
    try:
        response = xbee.wait_read_frame()
        #print("response is: {}".format(response)),
        for item in response:
            #print "item is",str(item)
            if (str(item) == 'source_addr_long') or (str(item) == 'source_addr'):
                print(item),
                print(response[item].encode("hex"))
            elif str(item) == 'samples':
                samplesDict = response[item]
                for x in samplesDict:
                    for y in x:
                        print(y),
                        print(x[y])
            else:
                print(item),
                print (response[item])
    except KeyboardInterrupt:
        break

ser.close()
