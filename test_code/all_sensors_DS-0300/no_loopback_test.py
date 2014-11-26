from Adafruit_BBIO.SPI import SPI 

spi = SPI(1,0) 
spi.mode=2 

spi.msh=200000 
spi.open(1,0) 

print spi.readbytes(4)
#print spi.xfer2([32, 11, 110, 22, 220]) 
spi.close() 
