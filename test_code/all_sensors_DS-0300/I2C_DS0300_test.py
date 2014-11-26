from Adafruit_I2C import Adafruit_I2C
import time

#Establish the I2C object, default address of 0x28
i2c_DS0300 = Adafruit_I2C(address=0x28, debug=True)

while (1):
  Response = i2c_DS0300.readList(reg=0,length=4)
  print "response is: ",Response

  #Extract/check Status bits:
  Status = (Response[0]>>6) & 0xFF
  print "Status bits are (in binary): ", format(Status,'02b')

  #Extract Pressure Value:
  Pressure = (((Response[0]<<2)>>2)<<8) + Response[1]
  #print "Pressure output is (in binary): ",format(Pressure,'014b')
  #print "Pressure output is (in hex): ",format(Pressure,'04x')
  #print "Pressure output is (in dec): ",Pressure
  #Calculate Pressure:
  Pressure_inH20 = 1.25*((float(Pressure)-8192)/(2**14))*4
  print "Pressure, converted is: ",format(Pressure_inH20,'0.6f'),"inH20"

  #Extract Temp Value:
  Temp = (Response[2]<<3)+(Response[3]>>5)
  #print "Temperature output is (in binary): ", format(Temp,'011b')
  #print "Temperature output is (in dec): ",Temp
  Temp_C = (float(Temp)*(float(200)/(2047)))-50
  print "Temp, converted is: ",Temp_C,"deg. C"
  time.sleep(5)

#Alternative ###
#import smbus
#bus = smbus.SMBus(1)
#response =  bus.read_byte(0x28)
#print "response is: ",response


