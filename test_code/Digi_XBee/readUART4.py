import Adafruit_BBIO.UART as UART
import serial
UART.setup("UART4")
UART.setup("UART2")
ser = serial.Serial(port = "/dev/ttyO4" , baudrate=9600)
ser.close()
ser.open()
print "Serial UART4 is open"
while ser.isOpen():
  inputPackets = list(ser.read(26))
  for item in inputPackets:
      print(str(item).encode("hex")),
  print("")
ser.close()

#UART.cleanup()


