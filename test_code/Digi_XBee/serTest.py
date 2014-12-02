import Adafruit_BBIO.UART as UART
import serial
UART.setup("UART4")
UART.setup("UART2")
ser = serial.Serial(port = "/dev/tty4" , baudrate=9600)
ser2 = serial.Serial(port = "/dev/tty2", baudrate=9600)
ser.close()
ser.open()
if ser.isOpen():
  print "Serial is open!"
  ser.write("Hello World!\r\n")
ser.close()

#UART.cleanup()


