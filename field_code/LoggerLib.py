#! /usr/bin/python

## LoggerLib.py -- Library for Combustion Monitoring 
## using BeagleBone Black (BBB) platform
##
## 2014-11-05 TimC - Initial
## 2014-11-07 TimC - put I2cs on their own; split out Adcs; added Temps, Ains, Burners and Timer; imported Decimal
## 2014-11-16 TimC - imported smbus; modified hierarchy; pushed many globals into classes; added burner code; using sleep v. signal in timer
## 2014-11-17 TimC - ...
## 2014-11-18 TimC - fix burner.status (was state); imported GPIO and upgraded Gpi and Gpo
## 2014-11-24 BenA - added pressure read detail to dlvr
## 2014-11-30 TimC - added use flag to Tc; improve the self-repair of sps and pga in Adc.startAdc(); I2c.errMsg now throws exception; assume both smbuses; switch to new print function; switch NaN to float 
## 2014-12-10 TimC - added sensor stat methods; added param classes for record control; added burnertc subclass for moving averages; brought in config; improved burner status and mode calculations
## 2014-12-12 TimC - prepare to enforce some more encapsulation; accommodate valve-switched sensors; 
## 2014.12.14 DanC - change default pga for ADCs from 1024 to 4096 full scale
##                 - added .extend for pressure sensors (also needed for co2?)
##                 - made significant revisions to calcMode()
## 2014-12-16 BenA - satisfied the records output header list. now to flesh out value capturing
## 2014-12-17 BenA - added unit conversions to the Sensor types 

from __future__ import print_function

import math, signal, time, gc
from datetime import datetime
from decimal import * ## https://docs.python.org/2/library/decimal.html
from smbus import SMBus
import Adafruit_BBIO.GPIO as GPIO
import LoggerConfig as Conf

######################################################
## buses, chips and protocols

class I2c(object):
    """includes all I2C(SMBus)-attached objects"""

    I2C1 = 0
    I2C2 = 1
    NI2C = 2

    smbuses = [SMBus(2), SMBus(1)]

    debug = False

    def __init__(self, name, i2cIndex, addr):
        self.name = name
        self.i2c = i2cIndex
        self.bus = I2c.smbuses[i2cIndex]
        self.addr = addr
        pass

    def errMsg(self, err):
        print("I2c[{}]: Error accessing 0x{:02x}: Check your I2C address".format(self.i2c, self.addr))
        raise err ## was return -1

    def write8(self, reg, datum):
        "Writes an 8-bit datum to the specified register/address"
        try:
            self.bus.write_byte_data(self.addr, reg, datum)
            if self.debug:
                print("I2c: Wrote 0x{:02x} to address 0x{:02x} register 0x{:02x}".format(datum, self.addr, reg))
        except IOError, err:
            return self.errMsg(err)

    def write16(self, reg, datum):
        "Writes a 16-bit datum to the specified register/address pair"
        try:
            self.bus.write_word_data(self.addr, reg, datum)
            if self.debug:
                print("I2c: Wrote 0x{:02x} to address 0x{:02x} register pair 0x{:02x},0x{:02x}".format(datum, self.addr, reg, reg+1))
        except IOError, err:
            return self.errMsg(err)

    def writeList(self, reg, data):
        "Writes an array of bytes using I2C format"
        try:
            if self.debug:
                print("I2c[{}]: Writing data to address 0x{:02x} at register 0x{:02x}: ".format(self.i2c, self.addr, reg), end='')
                for index in range(len(data)):
                    print(" 0x{:02x}".format(data[index]), end='')
                print()
            self.bus.write_i2c_block_data(self.addr, reg, data)
        except IOError, err:
            return self.errMsg(err)

    def readList(self, reg, length):
        "Read a array of bytes from the I2C device"
        try:
            data = self.bus.read_i2c_block_data(self.addr, reg, length)
            if self.debug:
                print("I2c[{}]: Reading data from address 0x{:02x} at register 0x{:02x}: ".format(self.i2c, self.addr, reg), end='')
                for index in range(len(data)):
                    print(" 0x{:02x}".format(data[index]), end='')
                print()
            return data
        except IOError, err:
            return self.errMsg(err)

    def readU8(self, reg):
        "Read an unsigned byte from the I2C device"
        try:
            result = self.bus.read_byte_data(self.addr, reg)
            if self.debug:
                print("I2C: Device 0x{:02x} returned 0x{:02x} from reg 0x{:02x}".format(self.addr, result & 0xFF, reg))
            return result
        except IOError, err:
            return self.errMsg(reg)

    def readS8(self, reg):
        "Reads a signed byte from the I2C device"
        try:
            result = self.bus.read_byte_data(self.addr, reg)
            if result > 127: result -= 256
            if self.debug:
                print("I2C: Device 0x{:02x} returned 0x{:02x} from reg 0x{:02x}".format(self.addr, result & 0xFF, reg))
            return result
        except IOError, err:
            return self.errMsg(err)

    def readU16(self, reg, little_endian=True):
        "Reads an unsigned 16-bit datum from the I2C device"
        try:
            result = self.bus.read_word_data(self.addr, reg)
            # Swap bytes if using big endian because read_word_data assumes little 
            # endian on ARM (little endian) systems.
            if not little_endian:
                result = ((result << 8) & 0xFF00) + (result >> 8)
            if (self.debug):
                print("I2C: Device 0x{:02x} returned 0x{:04x} from reg 0x{:02x}".format(self.addr, result & 0xFFFF, reg))
            return result
        except IOError, err:
            return self.errMsg(err)

    def readS16(self, reg, little_endian=True):
        "Reads a signed 16-bit datum from the I2C device"
        try:
            result = self.readU16(self.addr, reg, little_endian)
            if result > 32767: result -= 65536
            return result
        except IOError, err:
            return self.errMsg(err)

PGA = 4096    ## DWC 12.14 changed default from 1024 to 4096 
SPS = 250

class Adc(I2c):
    """includes all (I2C-attached) ADS1115-type ADC sensor inputs"""

    ## Much of the following logic was lifted from the startContinuousConversion() method
    ## in Adafruit_ADS1x15.py as of 2013-03 -- many thanks to K. Townsend, P. Villanueva et al.

    ## In the following Adafruit-derived code, 'channel' is what we elsewhere call 'mux'

    # IC Identifiers
    __IC_ADS1015                      = 0x00
    __IC_ADS1115                      = 0x01

    # Pointer Register
    __ADS1015_REG_POINTER_MASK        = 0x03
    __ADS1015_REG_POINTER_CONVERT     = 0x00
    __ADS1015_REG_POINTER_CONFIG      = 0x01
    __ADS1015_REG_POINTER_LOWTHRESH   = 0x02
    __ADS1015_REG_POINTER_HITHRESH    = 0x03

    # Config Register
    __ADS1015_REG_CONFIG_OS_MASK      = 0x8000
    __ADS1015_REG_CONFIG_OS_SINGLE    = 0x8000  # Write: Set to start a single-conversion
    __ADS1015_REG_CONFIG_OS_BUSY      = 0x0000  # Read: Bit = 0 when conversion is in progress
    __ADS1015_REG_CONFIG_OS_NOTBUSY   = 0x8000  # Read: Bit = 1 when device is not performing a conversion

    __ADS1015_REG_CONFIG_MUX_MASK     = 0x7000
    __ADS1015_REG_CONFIG_MUX_DIFF_0_1 = 0x0000  # Differential P = AIN0, N = AIN1 (default)
    __ADS1015_REG_CONFIG_MUX_DIFF_0_3 = 0x1000  # Differential P = AIN0, N = AIN3
    __ADS1015_REG_CONFIG_MUX_DIFF_1_3 = 0x2000  # Differential P = AIN1, N = AIN3
    __ADS1015_REG_CONFIG_MUX_DIFF_2_3 = 0x3000  # Differential P = AIN2, N = AIN3
    __ADS1015_REG_CONFIG_MUX_SINGLE_0 = 0x4000  # Single-ended AIN0
    __ADS1015_REG_CONFIG_MUX_SINGLE_1 = 0x5000  # Single-ended AIN1
    __ADS1015_REG_CONFIG_MUX_SINGLE_2 = 0x6000  # Single-ended AIN2
    __ADS1015_REG_CONFIG_MUX_SINGLE_3 = 0x7000  # Single-ended AIN3

    __ADS1015_REG_CONFIG_PGA_MASK     = 0x0E00
    __ADS1015_REG_CONFIG_PGA_6_144V   = 0x0000  # +/-6.144V range
    __ADS1015_REG_CONFIG_PGA_4_096V   = 0x0200  # +/-4.096V range
    __ADS1015_REG_CONFIG_PGA_2_048V   = 0x0400  # +/-2.048V range (default)
    __ADS1015_REG_CONFIG_PGA_1_024V   = 0x0600  # +/-1.024V range
    __ADS1015_REG_CONFIG_PGA_0_512V   = 0x0800  # +/-0.512V range
    __ADS1015_REG_CONFIG_PGA_0_256V   = 0x0A00  # +/-0.256V range

    __ADS1015_REG_CONFIG_MODE_MASK    = 0x0100
    __ADS1015_REG_CONFIG_MODE_CONTIN  = 0x0000  # Continuous conversion mode
    __ADS1015_REG_CONFIG_MODE_SINGLE  = 0x0100  # Power-down single-shot mode (default)

    __ADS1015_REG_CONFIG_DR_MASK      = 0x00E0  
    __ADS1015_REG_CONFIG_DR_128SPS    = 0x0000  # 128 samples per second
    __ADS1015_REG_CONFIG_DR_250SPS    = 0x0020  # 250 samples per second
    __ADS1015_REG_CONFIG_DR_490SPS    = 0x0040  # 490 samples per second
    __ADS1015_REG_CONFIG_DR_920SPS    = 0x0060  # 920 samples per second
    __ADS1015_REG_CONFIG_DR_1600SPS   = 0x0080  # 1600 samples per second (default)
    __ADS1015_REG_CONFIG_DR_2400SPS   = 0x00A0  # 2400 samples per second
    __ADS1015_REG_CONFIG_DR_3300SPS   = 0x00C0  # 3300 samples per second (also 0x00E0)

    __ADS1115_REG_CONFIG_DR_8SPS      = 0x0000  # 8 samples per second
    __ADS1115_REG_CONFIG_DR_16SPS     = 0x0020  # 16 samples per second
    __ADS1115_REG_CONFIG_DR_32SPS     = 0x0040  # 32 samples per second
    __ADS1115_REG_CONFIG_DR_64SPS     = 0x0060  # 64 samples per second
    __ADS1115_REG_CONFIG_DR_128SPS    = 0x0080  # 128 samples per second
    __ADS1115_REG_CONFIG_DR_250SPS    = 0x00A0  # 250 samples per second (default)
    __ADS1115_REG_CONFIG_DR_475SPS    = 0x00C0  # 475 samples per second
    __ADS1115_REG_CONFIG_DR_860SPS    = 0x00E0  # 860 samples per second

    __ADS1015_REG_CONFIG_CMODE_MASK   = 0x0010
    __ADS1015_REG_CONFIG_CMODE_TRAD   = 0x0000  # Traditional comparator with hysteresis (default)
    __ADS1015_REG_CONFIG_CMODE_WINDOW = 0x0010  # Window comparator

    __ADS1015_REG_CONFIG_CPOL_MASK    = 0x0008
    __ADS1015_REG_CONFIG_CPOL_ACTVLOW = 0x0000  # ALERT/RDY pin is low when active (default)
    __ADS1015_REG_CONFIG_CPOL_ACTVHI  = 0x0008  # ALERT/RDY pin is high when active

    __ADS1015_REG_CONFIG_CLAT_MASK    = 0x0004  # Determines if ALERT/RDY pin latches once asserted
    __ADS1015_REG_CONFIG_CLAT_NONLAT  = 0x0000  # Non-latching comparator (default)
    __ADS1015_REG_CONFIG_CLAT_LATCH   = 0x0004  # Latching comparator

    __ADS1015_REG_CONFIG_CQUE_MASK    = 0x0003
    __ADS1015_REG_CONFIG_CQUE_1CONV   = 0x0000  # Assert ALERT/RDY after one conversions
    __ADS1015_REG_CONFIG_CQUE_2CONV   = 0x0001  # Assert ALERT/RDY after two conversions
    __ADS1015_REG_CONFIG_CQUE_4CONV   = 0x0002  # Assert ALERT/RDY after four conversions
    __ADS1015_REG_CONFIG_CQUE_NONE    = 0x0003  # Disable the comparator and put ALERT/RDY in high state (default)
    
    
    # Dictionaries with the sampling speed values
    # These simplify and clean the code (avoid the abuse of if/elif/else clauses)
    spsADS1115 = {
      8:__ADS1115_REG_CONFIG_DR_8SPS,
      16:__ADS1115_REG_CONFIG_DR_16SPS,
      32:__ADS1115_REG_CONFIG_DR_32SPS,
      64:__ADS1115_REG_CONFIG_DR_64SPS,
      128:__ADS1115_REG_CONFIG_DR_128SPS,
      250:__ADS1115_REG_CONFIG_DR_250SPS,
      475:__ADS1115_REG_CONFIG_DR_475SPS,
      860:__ADS1115_REG_CONFIG_DR_860SPS
    }    
    spsADS1015 = {
      128:__ADS1015_REG_CONFIG_DR_128SPS,
      250:__ADS1015_REG_CONFIG_DR_250SPS,
      490:__ADS1015_REG_CONFIG_DR_490SPS,
      920:__ADS1015_REG_CONFIG_DR_920SPS,
      1600:__ADS1015_REG_CONFIG_DR_1600SPS,
      2400:__ADS1015_REG_CONFIG_DR_2400SPS,
      3300:__ADS1015_REG_CONFIG_DR_3300SPS
    }
    # Dictionary with the programmable gains
    pgaADS1x15 = {
      6144:__ADS1015_REG_CONFIG_PGA_6_144V,
      4096:__ADS1015_REG_CONFIG_PGA_4_096V,
      2048:__ADS1015_REG_CONFIG_PGA_2_048V,
      1024:__ADS1015_REG_CONFIG_PGA_1_024V,
      512:__ADS1015_REG_CONFIG_PGA_0_512V,
      256:__ADS1015_REG_CONFIG_PGA_0_256V
    }    

    debug = False
    addrs = [ 0x48, 0x49, 0x4a, 0x4b ]

    def __init__(self, name, i2cIndex, adcIndex, addrIndex):
        I2c.__init__(self, name, i2cIndex, Adc.addrs[addrIndex])
        self.ic = Adc.__IC_ADS1115 ## our chosen hardware
        self.adc = adcIndex
        #self.addrIndex = addrIndex
        #self.sps ## set later
        #self.pga ## set later
        #self.startTime ## set later
        pass

    def startAdc(self, channel, pga=PGA, sps=SPS): 
        if Adc.debug: 
            print("adc: {}: starting continuous ADC at sps: {}".format(self.name, sps))

        # Disable comparator, Non-latching, Alert/Rdy active low
        # traditional comparator, continuous mode
        # The last flag is the only change we need, page 11 datasheet
        config = Adc.__ADS1015_REG_CONFIG_CQUE_NONE    | \
                 Adc.__ADS1015_REG_CONFIG_CLAT_NONLAT  | \
                 Adc.__ADS1015_REG_CONFIG_CPOL_ACTVLOW | \
                 Adc.__ADS1015_REG_CONFIG_CMODE_TRAD   | \
                 Adc.__ADS1015_REG_CONFIG_MODE_CONTIN    

        # Set sample per seconds, defaults to 250sps
        # If sps is in the dictionary (defined in init()) it returns the value of the constant
        # othewise it returns the value for 250sps. This saves a lot of if/elif/else code!
        if (self.ic == Adc.__IC_ADS1015):
            config |= Adc.spsADS1015.setdefault(sps, Adc.__ADS1015_REG_CONFIG_DR_1600SPS)
        else:
            if ( (sps not in Adc.spsADS1115) ): ## was wrongly using '&' v. 'and'; also, did not correct the value unless debug was on
                if (self.debug):
                    print("ADS1x15: Invalid sps specified: {}, using 250".format(sps))## was wrong message
                sps = 250 ## this set was missing in Adafruit
            config |= Adc.spsADS1115.setdefault(sps, Adc.__ADS1115_REG_CONFIG_DR_250SPS)
        self.sps = sps ## save for fetchResult
      
        # Set PGA/voltage range, defaults to +-6.144V
        if ( (pga not in Adc.pgaADS1x15) ): ## was wrongly using '&' v. 'and'; also, did not correct the value unless debug was on
            if (self.debug):
                print("ADS1x15: Invalid pga specified: {}, using 6144mV".format(pga))
            pga = 6144 ## this set was missing in Adafruit
        config |= Adc.pgaADS1x15.setdefault(pga, Adc.__ADS1015_REG_CONFIG_PGA_6_144V)
        self.pga = pga ## save for fetchResult
        
        # Set the channel to be converted
        if channel == 3:
            config |= Adc.__ADS1015_REG_CONFIG_MUX_SINGLE_3
        elif channel == 2:
            config |= Adc.__ADS1015_REG_CONFIG_MUX_SINGLE_2
        elif channel == 1:
            config |= Adc.__ADS1015_REG_CONFIG_MUX_SINGLE_1
        else:
            config |= Adc.__ADS1015_REG_CONFIG_MUX_SINGLE_0    
      
        # Set 'start single-conversion' bit to begin conversions
        # No need to change this for continuous mode!
        config |= Adc.__ADS1015_REG_CONFIG_OS_SINGLE

        # Write config register to the ADC
        # Once we write the ADC will convert continously
        # we can read the next values using getLastConversionResult
        bytes = [(config >> 8) & 0xFF, config & 0xFF]
        self.writeList(Adc.__ADS1015_REG_POINTER_CONFIG, bytes)
        self.startTime = time.time()
        pass

    def fetchAdc(self):
        # Read the conversion results from startAdc()
        result = self.readList(Adc.__ADS1015_REG_POINTER_CONVERT, 2)
        if (self.ic == Adc.__IC_ADS1015):
            # Shift right 4 bits for the 12-bit ADS1015 and convert to mV
            return ( ((result[0] << 8) | (result[1] & 0xFF)) >> 4 )*self.pga/2048.0
        else:
            # Return a mV value for the ADS1115
            # (Take signed values into account as well)
            try:
                val = (result[0] << 8) | (result[1])
                if val > 0x7FFF:
                    return (val - 0xFFFF)*self.pga/32768.0
                else:
                    return ( (result[0] << 8) | (result[1]) )*self.pga/32768.0
            except TypeError, err:
                print("fetchAdc result \"{}\"  error: {}".format(result, err))
                raise err

        pass

    U11 = 0
    U13 = 1
    U14 = 2
    U15 = 3
    U8 = 4
    U9 = 5
    U10 = 6
    NADC = 7

    ADDR0 = 0
    ADDR1 = 1
    ADDR2 = 2
    ADDR3 = 3

    MUX0 = 0
    MUX1 = 1
    MUX2 = 2
    MUX3 = 3
    NMUX = 4

adcs = [
        Adc("TC_ADC@U11", I2c.I2C1, Adc.U11, Adc.ADDR0),
        Adc("TC_ADC@U13", I2c.I2C1, Adc.U13, Adc.ADDR1),
        Adc("TC_ADC@U14", I2c.I2C1, Adc.U14, Adc.ADDR2),
        Adc("TC_ADC@U15", I2c.I2C1, Adc.U15, Adc.ADDR3),

        Adc("JP1_ADC@U8", I2c.I2C2, Adc.U8, Adc.ADDR0),
        Adc("J25_ADC@U9", I2c.I2C2, Adc.U9, Adc.ADDR1),
        Adc("J25_ADC@U10", I2c.I2C2, Adc.U10, Adc.ADDR2),
    ]

## end of busses, chips and protocols
######################################################
## sensors and values

NaN = float('NaN')

class Sensor(object):
    """includes all sensor inputs"""

    def __init__(self, name):
        self.name = name
        #self.values = collections.deque()
        self.values = list() ## https://docs.python.org/2/library/stdtypes.html#typesseq-mutable 
        pass

    def clearValues():
        self.values = list()
        pass

    def appendValue(self, value):
        self.values.append(value)
        pass

    def getLastVal(self):
        return NaN if len(self.values) <= 0 else self.values[-1]
        pass

    def getPrevVal(self):
        return NaN if len(self.values) <= 1 else self.values[-2]
        pass

    def getValCnt(self):
        return len(self.values)

    def getAvgVal(self):
        return NaN if len(self.values) <= 0 else math.fsum(self.values)/len(self.values)

    def getMinVal(self):
        return NaN if len(self.values) <= 0 else min(self.values)

    def getMaxVal(self):
        return NaN if len(self.values) <= 0 else max(self.values)

sensors = []

class Ain(Sensor):
    """includes all (ADC-attached) analog inputs"""

    def __init__(self, name, adcIndex, mux, use=True, pga=PGA, sps=SPS):
        Sensor.__init__(self, name)
        self.adcIndex = adcIndex
        self.adc = adcs[adcIndex]
        self.mux = mux
        self.use = use
        self.pga = pga
        self.sps = sps
        pass

    def startAdc(self, channel, pga=PGA, sps=SPS): 
        self.adc.startAdc(channel, pga=PGA, sps=SPS) 
        self.pga = self.adc.pga ## in case it was changed
        self.sps = self.adc.sps ## in case it was changed
        
    def fetchAdc(self):
        return self.adc.fetchAdc()

    def appendAdcValue(self, value):
        self.appendValue(value)
        pass

ains = []

class Tc(Ain):
    """includes all (ADC-attached) AD8495-type thermocouple sensor inputs"""

    def __init__(self, name, adcIndex, mux, use=True, pga=PGA, sps=SPS):
        Ain.__init__(self, name, adcIndex, mux, use, pga, sps)
        pass

    def appendAdcValue(self, value): ## override
        value = value ## convert to temp
        Volts = value/1000
        if (self.name == "TC15@U15") or (self.name=="TC16@U15"):
            result = (360*(Volts-0.5))+32 #for deg. F, 0.5V bias
        else:
            result = (360*Volts)+32 #for deg. F
            #print("{} \tResult: {}F, Gain:{}, I2C Address: 0x{:02x},Input:{}"\  ## See new print below
            #    .format(sensor.name,result,adc.pga,adc.addrs[sensor.adcIndex],sensor.mux))
        self.appendValue(result)
        pass

class BurnerTc(Tc):
    """includes all (ADC-attached) AD8495-type thermocouple sensor inputs acquiring burner temperatures"""
    def __init__(self, name, adcIndex, mux, use=True, pga=PGA, sps=SPS):
        Tc.__init__(self, name, adcIndex, mux, use, pga, sps)
        self.recent = list() ## never cleared--just truncated
        pass

    def appendValue(self, value):
        Tc.appendValue(self, value) ## https://docs.python.org/2/tutorial/classes.html#inheritance
        self.recent.append(value)
        while (len(self.recent) > 10):
            del(self.recent[0])
        pass

    def getMovAvg(self):
        return NaN if len(self.recent) <= 0 else math.fsum(self.recent)/len(self.recent)

tcs = [
  BurnerTc("TC1@U11", Adc.U11, Adc.MUX0),
        Tc("TC2@U11", Adc.U11, Adc.MUX1),
        Tc("TC3@U11", Adc.U11, Adc.MUX2),
        Tc("TC4@U11", Adc.U11, Adc.MUX3),

        Tc("TC5@U13", Adc.U13, Adc.MUX0),
        Tc("TC6@U13", Adc.U13, Adc.MUX1),
  BurnerTc("TC7@U13", Adc.U13, Adc.MUX2),
        Tc("TC8@U13", Adc.U13, Adc.MUX3),

        Tc("TC9@U14",  Adc.U14, Adc.MUX0),
        Tc("TC10@U14", Adc.U14, Adc.MUX1),
        Tc("TC11@U14", Adc.U14, Adc.MUX2),
        Tc("TC12@U14", Adc.U14, Adc.MUX3),

        Tc("TC13@U15", Adc.U15, Adc.MUX0),
        Tc("TC14@U15", Adc.U15, Adc.MUX1),
        Tc("TC15@U15", Adc.U15, Adc.MUX2), ## TODO
        Tc("TC16@U15", Adc.U15, Adc.MUX3), ## spare tc
    ]

ains.extend(tcs)

class CO(Ain):
    """includes all (ADC-attached) CO sensor inputs"""
    def __init__(self, name, adcIndex, mux, pga=PGA, sps=SPS, co_calib_value=1658):
        Ain.__init__(self, name, adcIndex, mux, pga=PGA, sps=SPS)
        self.co_calib_value = co_calib_value
        pass
    
    def appendAdcValue(self, value):
        value = value
        volts = value/1000  ## TODO get this converted to engineering units, and test 
        result = ((volts * 0.5) * 2.326e6) / self.co_calib_value
        self.appendValue(result)
        pass

door1 = Ain("JP1-A@U8", Adc.U8, Adc.MUX0) ## door1 pose
fan1 = Ain("JP1-B@U8", Adc.U8, Adc.MUX1) ## fan current 1 sensor
fan2 = Ain("JP1-C@U8", Adc.U8, Adc.MUX2) ## fan current 2 sensor
co   = CO("JP1-D@U8", Adc.U8, Adc.MUX3) ## CO sensor
ains.extend([door1, fan1, fan2, co]) ## remaining ains NOT included: [co2..., niu1, niu2, batt, niu3, niu4, niu5, niu6])
sensors.extend(ains) 

## note: remaining sensors are more complicated...what with valves and all...and are handled separately

class CO2(Ain):
    """includes all (ADC-attached) CO2 sensor inputs"""
    valve_whvent = 0 ## 5
    valve_fvent = 1 ## 6
    valve_zone = 2 ## 7

    def __init__(self, name, adcIndex, mux, valve, pga=PGA, sps=SPS):
        Ain.__init__(self, name, adcIndex, mux, pga=PGA, sps=SPS)
        self.valve = valve
        pass

    def setValves(self):
        ## sets all valves as appropriate for sampling this co2 sensor's nominal location
        ## --should be called as early as possible before the adc
        for valve in range(len(co2_valves)): ##[CO2.valve_whvent, CO2.valve_fvent, CO2.valve_zone]: ## set the valves per the ctor arg
            co2_valves[valve].setValue(valve == self.valve)
        co2_valve_pos.setValue(self.valve) ## set the ad hoc param value for reporting valve position
        co2_valve_time.setValue(now()) ## set the ad hoc param value for reporting valve open time--TODO should be elapsed time

    def appendAdcValue(self, value):
        value = value
        volts = value/1000  ## TODO get this converted to engineering units
        self.appendValue(volts)
        pass

co2_whvent = CO2("J25-1@U9", Adc.U9, Adc.MUX0, CO2.valve_whvent) ## valve-switched--unique CO2 sensor on same ADC
co2_fvent = CO2("J25-1@U9", Adc.U9, Adc.MUX0, CO2.valve_fvent) ## valve-switched--unique CO2 sensor on same ADC
co2_zone  = CO2("J25-1@U9", Adc.U9, Adc.MUX0, CO2.valve_zone) ## valve-switched--unique CO2 sensor on same ADC
co2_sensors = [co2_whvent, co2_fvent, co2_zone]

niu1 = Ain("J25-2@U9", Adc.U9, Adc.MUX1) ## unused ain
niu2 = Ain("J25-3@U9", Adc.U9, Adc.MUX2) ## unused ain
batt = Ain("J25-4@U9", Adc.U9, Adc.MUX3) ## battery voltage sensor

niu3 = Ain("J25-5@U10", Adc.U10, Adc.MUX0) ## spare ain
niu4 = Ain("J25-6@U10", Adc.U10, Adc.MUX1) ## spare ain
niu5 = Ain("J25-7@U10", Adc.U10, Adc.MUX2) ## spare ain
niu6 = Ain("J25-8@U10", Adc.U10, Adc.MUX3) ## spare ain

## DWC 12.14 need ain.extend and sensors.extend for these: [co2..., niu1, niu2, batt, niu3, niu4, niu5, niu6]

class Dlvr(I2c, Sensor):
    """includes the (I2C-attached) DLVR pressure sensor input"""

    valve_zero = 0 ## 1
    valve_whvent = 1 ## 2
    valve_fvent = 2 ## 3
    valve_zone = 3 ## 4

    def __init__(self, name, i2cIndex, valve):
        I2c.__init__(self, name, i2cIndex, addr=0x28)
        Sensor.__init__(self, name)
        self.valve = valve
        pass

    def setValves(self):
        ## sets all valves as appropriate for sampling this pressure sensor's nominal location
        ## --should be called as early as possible before the reading?
        for valve in range(len(p_valves)): ##[Dlvr.valve_zero, Dlvr.valve_whvent, Dlvr.valve_fvent, Dlvr.valve_zone]: ## set the valves per the ctor arg
            p_valves[valve].setValue(valve == self.valve)
        p_valve_pos.setValue(self.valve) ## set the ad hoc param value for reporting valve position
        p_valve_time.setValue(now()) ## set the ad hoc param value for reporting valve open time--TODO should be elapsed time

    def readPressure(self):
        Response = self.readList(reg=0,length=4)
        Status = (Response[0]>>6) & 0xFF
        #print "Status bits are (in binary): ", format(Status,'02b')
        if Status != 0:
            #print "Pressure Data not Ready!"
            return float('NaN')
        else:
            #Extract Pressure Value:
            Pressure = (((Response[0]<<2)>>2)<<8) + Response[1]
            #print "Pressure output is (in binary): ",format(Pressure,'014b')
            #print "Pressure output is (in hex): ",format(Pressure,'04x')
            #print "Pressure output is (in dec): ",Pressure
            #Calculate Pressure:
            Pressure_inH20 = 1.25*((float(Pressure)-8192)/(2**14))*4
            #print "Pressure, converted is: ",format(Pressure_inH20,'0.6f'),"inH20"
            #Extract Temp Value:
            #Temp = (Response[2]<<3)+(Response[3]>>5)
            #print "Temperature output is (in binary): ", format(Temp,'011b')
            #print "Temperature output is (in dec): ",Tem
            #Temp_C = (float(Temp)*(float(200)/(2047)))-50
            #print "Temp, converted is: ",Temp_C,"deg. C"
            return Pressure_inH20
        pass

p_zero = Dlvr("DLVR@U12", I2c.I2C1, Dlvr.valve_zero)
p_whvent = Dlvr("DLVR@U12", I2c.I2C1, Dlvr.valve_whvent)
p_fvent = Dlvr("DLVR@U12", I2c.I2C1, Dlvr.valve_fvent)
p_zone = Dlvr("DLVR@U12", I2c.I2C1, Dlvr.valve_zone)
p_sensors = [p_zero, p_whvent, p_fvent, p_zone]

## DWC 12.14 add sensors.extend here
##  Note does NOT use ains.extend like: ains.extend([door1, fan1, fan2, co]) 
sensors.extend(p_sensors) 


class Rtc(I2c):
    """includes the (I2C-attached) RTC clock input/ouput"""
    def __init__(self, name, i2cIndex):
        I2c.__init__(self, name, i2cIndex, addr=0x66) ## TODO
        pass

rtc = Rtc("RTC@U4", I2c.I2C1)
#sensors.extend([rtc]) ## not a sensor

class Xbee(Sensor):
    """includes all XBEE wireless linked sensor nodes"""
    def __init__(self, name, adcIndex,address,use=True):
        Sensor.__init__(self, name)
        self.name = name
        self.adcIndex = adcIndex
        self.adc = "adc-"+str(adcIndex+1)
        self.address = address
        self.use = use
        pass

    def appendAdcValue(self, value):
        value = value 
        #print '\t'+str(self.name),value*0.001173,"volts",sensor.adc
        volts = value*0.001173 # per xbee adc conversion to volts
        self.appendValue(volts)
        pass

xbee = []  #these are to be defined in LoggerMain from LoggerConfig values 
sensors.extend(xbee)

P8_7 = 7
P8_8 = 8
P8_9 = 9
P8_10 = 10
P8_11 = 11
P8_12 = 12
P8_13 = 13
P8_14 = 14
P8_15 = 15

P8_16 = 16
P8_17 = 17

class Gpi(Sensor):
    """includes all GPIO-attached sensor inputs"""
    def __init__(self, name, pin):
        Sensor.__init__(self, name)
        self.pin = pin
        GPIO.setup(pin, GPIO.IN)
        pass
    
    def getValue(self):
        return GPIO.input(self.pin)

sw1 = Gpi("SW1@P8-16", "P8_16") ## spare
sw2 = Gpi("SW2@P8-17", "P8_17") ## spare
sensors.extend([sw1, sw2])

############################################
## control outputs

class Control(object):
    """includes all control outputs"""
    def __init__(self, name):
        self.name = name
        pass

class Gpo(Control):
    """includes all GPIO-attached control outputs"""
    def __init__(self, name, pin):
        Control.__init__(self, name)
        self.pin = pin
        GPIO.setup(pin, GPIO.OUT)
        pass

    def setValue(self, value):
        GPIO.output(self.pin, GPIO.HIGH if (value) else GPIO.LOW)
        pass

controls = [
        Gpo("S01@P8-7", "P8_7"),   ## p_zero
        Gpo("S02@P8-8", "P8_8"),   ## p_whvent
        Gpo("S03@P8-9", "P8_9"),   ## p_fvent
        Gpo("S04@P8-10", "P8_10"), ## p_zone
        Gpo("S05@P8-11", "P8_11"), ## co2_whvent
        Gpo("S06@P8-12", "P8_12"), ## co2_fvent
        Gpo("S07@P8-13", "P8_13"), ## co2_zone
        Gpo("S08@P8-14", "P8_14"), ## Pump

        Gpo("24V@P8-15", "P8_15"), ## switch for 24V pwr
    ]

p_zero_valve = controls[0]
p_whvent_valve = controls[1]
p_fvent_valve = controls[2]
p_zone_valve = controls[3]
p_valves = [p_zero_valve, p_whvent_valve, p_fvent_valve, p_zone_valve]

co2_whvent_valve = controls[4]
co2_fvent_valve = controls[5]
co2_zone_valve = controls[6]
co2_valves = [co2_whvent_valve, co2_fvent_valve, co2_zone_valve]

############################################
## burners

class Burner(object):
    """includes all (both) burners"""
    Mode0NotPresent = 0
    Mode1JustStarted = 1
    Mode2On = 2
    Mode3JustStopped = 3
    Mode4Cooling = 4
    Mode5Off = 5

    T_WHFLUEMIN = 120 ## F
    T_FFLUEMIN = 120 ## F

    STATUS_ON = True
    STATUS_OFF = False

    def __init__(self, name, dtOn, dtOff, tcIndex, isPresent):
        self.name = name
        self.dtOn = dtOn ## deg. F delta
        self.dtOff = dtOff ## deg. F delta
        #self.tcIndex = tcIndex ## not needed--and may be overridden
        self.tc = tcs[tcIndex]
        self.isPresent = isPresent
        self.startTime = None
        self.stopTime = None
        self.status = Burner.STATUS_OFF
        self.prevStatus = Burner.STATUS_OFF   ## DWC 12.14 was  self.prevStatus = None, OK if set at top of calcStatus()
        self.mode = self.Mode5Off         ## DWC 12.14 was  self.mode = None
        self.prevMode = None     ## DWC 12.14 was  self.prevMode = None, OK if set at top of calcMode()
        pass

    def calcStatus(self):
        self.prevStatus = self.status
        last = self.tc.getLastVal()
        if (last != NaN):
            avg = self.tc.getMovAvg()
            if ((last - avg) > self.dtOn):
                self.status = Burner.STATUS_ON
            elif ((last - avg) < self.dtOff):
                self.status = Burner.STATUS_OFF
            #else no change
        return self.status

    def getStatus(self):
        return self.status

    """    
    ## DWC 12.14 not used - incorporated below
    def iscooling(self):      
        cooling = False
        if (self.stopTime is not None):
            coolTime = self.stopTime + 180.0 ## plus 3 minutes...
            coolDateTime = datetime.utcfromtimestamp(coolTime)
            coolTime -= (coolDateTime.second + (coolDateTime.microsecond / 1000000.0)) ## ...then back up to top of the minute
            cooling = True if (time.time() < coolTime) else False
        return cooling
        pass
    """
    ## DWC 12.14 Major revision
    def calcMode(self):
        """N.B. this method also sets the stopTime which is used in the calculation--must be called once and only once every tick"""
        ## self.mode = Burner.Mode0NotPresent  Why would this be here - covered in initialization
        if (self.isPresent):
            self.prevMode = self.mode     ## Moved up from end
            self.calcStatus() ## update status
            self.timeOn = 0.0  ## set in mode calcs as needed
            ## DWC 12.14 drop: self.mode = Burner.Mode2On if (self.status == Burner.STATUS_ON) else Burner.Mode5Off
            ## DWC 12.14 don't think we need this if values are intialized:
            #if (self.prevMode is not None):
            if (self.prevMode == Burner.Mode1JustStarted):
                if (self.status == Burner.STATUS_ON):
                    self.mode = Burner.Mode2On
                    self.timeOn = now() - self.startTime
                else:
                    self.mode = Burner.Mode4Cooling
                    ## unexpected--register an error
                    self.stopTime = now()
            elif (self.prevMode == Burner.Mode2On):
                if (self.status == Burner.STATUS_OFF):
                    self.mode = Burner.Mode3JustStopped
                    self.timeOn = now() - self.startTime
                    self.stopTime = now()
                else:
                    self.timeOn = now() - self.startTime
                    ## no change in mode
            elif (self.prevMode == Burner.Mode3JustStopped):
                if (self.status == Burner.STATUS_OFF):
                    self.mode = Burner.Mode4Cooling
                    self.timeCooling = now() - self.stopTime
                else:
                    self.mode = Burner.Mode1JustStarted
                    ## unexpected--register an error
                    self.startTime = now()
            elif (self.prevMode == Burner.Mode4Cooling):
                if (self.status == Burner.STATUS_OFF):
                    self.timeCooling = now() - self.stopTime
                    ## elapsed = math.trunc(now() - self.stopTime)  Need math.trunc??
                    if (((self.timeCooling >= 120) and ((self.timeCooling % 60) == 0))\
                    or (self.timeCooling >= 180)\
                    or (self.timeCooling <= -10)):  ## Check for large negative error
                        self.mode = Burner.Mode5Off
                    ## Else stay in Mode4Cooling
                else:
                    self.mode = Burner.Mode1JustStarted
                    self.startTime = now()
            elif (self.prevMode == Burner.Mode5Off):
                if (self.status == Burner.STATUS_ON):
                    self.mode = Burner.Mode1JustStarted
                    self.startTime = now()
                ## Else stay in Mode5Off
        return self.mode


    def getMode(self):
        return self.mode

waterHeaterIsPresent = (Conf.waterHeaterIsPresent is not None and Conf.waterHeaterIsPresent == True)
furnaceIsPresent = (Conf.furnaceIsPresent is not None and Conf.furnaceIsPresent == True)

## Set dTemps for identifying burner turn on and turn off in constructors
waterHtr = Burner("waterHtr", 5, -2, 0, waterHeaterIsPresent)
furnace = Burner("furnace", 5, -2, 6, furnaceIsPresent)
burners = [waterHtr, furnace]

############################################
## misc / ancillary

def now():
    return time.time()

class Timer(object):
    """time manager"""
    lastTick = now()
    awake = True

    @staticmethod
    def __signalHandler__(sig, frm):
        if Timer.awake: 
            print("alarmed while awake")
        pass

    @staticmethod
    def nap():
        """sleep till top of second"""
        time.sleep((10.0**6 - datetime.utcfromtimestamp(now()).microsecond) / 10.0**6)

    @staticmethod
    def start():
        signal.signal(signal.SIGALRM, Timer.__signalHandler__)
        #signal.setitimer(signal.ITIMER_REAL, 1, 1)
        Timer.awake = False
        Timer.nap()
        Timer.awake = True
        Timer.lastTick = now()
        pass

    @staticmethod
    def sleep():
        gc.enable()
        Timer.awake = False

        #time.sleep(1)
        Timer.nap()
        Timer.lastTick = now()

        Timer.awake = True
        gc.disable()
        pass

    @staticmethod
    def stime():
        return Timer.lastTick
        pass

############################################
## record parameters

def TIME(tm):
    return time.strftime("\"%Y-%m-%d %H:%M:%S\"",time.gmtime(tm))

class Param(object):
    """includes all parameters to be reported"""

    def __init__(self, headers, units=[""], values=[""]):
        self.headers = headers
        self.units = units
        self.values = values

    def reportHeaders(self):
        return self.headers

    def reportUnits(self):
        return self.units ## len must match headers

    def reportScanData(self): ## len must match headers and units
        return self.values

    def reportStatData(self): ## len must match headers and units
        return self.values

    def setValue(self, value): ## storage for ad hoc params
        if (len(self.values) <= 0): 
            self.values.append(value)
        else: 
            self.values[0] = value

siteid = Param(["site"], [""], [Conf.siteName])
timest = Param(["time"], ["UTC"], [TIME(Timer.stime())])
recnum = Param(["rec_num"],["integer"],[0])

params = [siteid, timest, recnum] ## alnum, utc, int

def DEC(number):
    return Decimal(number) #"{:d}".format(number)

class SampledParam(Param):
    """includes all sensed/sampled parameters to be reported"""

    def __init__(self, headers, units, loc, sensor):
        Param.__init__(self, headers, units)
        self.loc = loc
        self.sensor = sensor

    def dur(self):
        return TIME(self.sampleDuration())

    def val(self):
        return DEC(self.sensor.getLastVal())

    def avgVal(self):
        return DEC(self.sensor.getAvgVal())

    def minVal(self):
        return DEC(self.sensor.getMinVal())

    def maxVal(self):
        return DEC(self.sensor.getMaxVal())

    def valCnt(self):
        return self.sensor.getValCnt()

    def other(self):
        return "other"

    def reportScanData(self): ## len must match headers and units
        return [self.val(), self.val(), self.val()]

    def reportStatData(self): ## len must match headers and units
        return [self.avgVal(), self.minVal(), self.maxVal()]

class TempParam(SampledParam):
    """includes all TC (sampled) parameters"""
    def __init__(self, loc, sensor):
        SampledParam.__init__(self, [loc+"", loc+"_min", loc+"_max"], ["deg. F", "deg. F", "deg. F"], loc, sensor) 

t_whburner = TempParam("t_whburner", tcs[0])
t_whspill1 = TempParam("t_whspill1", tcs[1])
t_whspill2 = TempParam("t_whspill2", tcs[2])
t_whspill3 = TempParam("t_whspill3", tcs[3])
t_whspill4 = TempParam("t_whspill4", tcs[4])
t_whvent = TempParam("t_whvent", tcs[5])
params.extend([t_whburner, t_whspill1, t_whspill2, t_whspill3, t_whspill4, t_whvent])

t_fburner = TempParam("t_fburner", tcs[6])
t_fspill1 = TempParam("t_fspill1", tcs[7])
t_fspill2 = TempParam("t_fspill2", tcs[8])
t_fspill3 = TempParam("t_fspill3", tcs[9])
t_fspill4 = TempParam("t_fspill4", tcs[10])
t_fvent = TempParam("t_fvent", tcs[11])
params.extend([t_fburner, t_fspill1, t_fspill2, t_fspill3, t_fspill4, t_fvent])

t_zonehi = TempParam("t_zonehi", tcs[12])
t_zonelow = TempParam("t_zonelow", tcs[13])
t_outdoor = TempParam("t_outdoor", tcs[14])
t_extra = TempParam("t_extra", tcs[15])
params.extend([t_zonehi, t_zonelow, t_outdoor, t_extra])

class AinParam(SampledParam):
    """includes all AIN (sampled) parameters"""
    def __init__(self, loc, sensor):
        SampledParam.__init__(self, [loc+"", loc+"_min", loc+"_max"], ["V", "V", "V"], loc, sensor) 

pos_door1 = AinParam("pos_door1", door1) ## TODO
i_fan1 = AinParam("i_fan1", fan1)
i_fan2 = AinParam("i_fan2", fan2)
params.extend([pos_door1, i_fan1, i_fan2]) ## Bool, Amps, Amps TODO

ppm_co = AinParam("ppm_co", co) ## TODO
params.extend([ppm_co])

class CO2Param(SampledParam):
    """includes all CO2 (sampled) parameters"""
    def __init__(self, loc, sensor):
        fix = "ppm_co2_"+loc
        SampledParam.__init__(self, [fix+"", fix+"_min", fix+"_max"], ["ppm", "ppm", "ppm"], loc, sensor) 

    def reportScanData(self): ## override
        return [self.val(), self.val(), self.val()]

    def reportStatData(self): ## override
        return [self.avgVal(), self.minVal(), self.maxVal()]

co2_valve_pos = Param(["loc_co2"],["integer"],[DEC(NaN)]) ## ad hoc param for reporting co2 valve position
co2_valve_time = Param(["sec_co2"],["integer"],[0]) ## ad hoc param for reporting co2 valve open time--TODO: should report duration
whventco2 = CO2Param("whvent", co2_whvent)
fventco2 = CO2Param("fvent", co2_fvent)
zoneco2 = CO2Param("zone", co2_zone)
params.extend([co2_valve_pos, co2_valve_time, whventco2, fventco2, zoneco2])

class PressureParam(SampledParam):
    """includes all pressure (sampled) parameters"""
    def __init__(self, loc, sensor):
        fix = "p_"+loc
        SampledParam.__init__(self, [fix+"", fix+"_min", fix+"_max", fix+"_rng", fix+"_rng_min", fix+"_rng_max"], ["kpa", "kpa", "kpa", "kpa", "kpa", "kpa"], loc, sensor) 

    def reportScanData(self): ## override
        return [self.val(), self.val(), self.val(), self.val(), self.val(), self.val()] #TODO change range value outputs to match
 
    def reportStatData(self): ## override
        return [self.avgVal(), self.minVal(), self.maxVal(), (self.maxVal()-self.minVal()), self.minVal(), self.maxVal()] #TODO change range value outputs

p_valve_pos = Param(["loc_p"],["integer"],[DEC(NaN)]) ## ad hoc param for reporting pressure valve position
p_valve_time = Param(["sec_p"],["integer"],[0]) ## ad hoc param for reporting pressure valve open time--TODO: should report duration
zeropress = PressureParam("zero", p_zero) ## TODO: these should be different sensors
whventpress = PressureParam("whvent", p_whvent)
fventpress = PressureParam("fvent", p_fvent)
zonepress = PressureParam("zone", p_zone)
params.extend([p_valve_pos, p_valve_time, zeropress, whventpress, fventpress, zonepress])

whburner = Param(["wh_status", "wh_mode"],["integer","integer"],[DEC(NaN),DEC(NaN)]) #TODO check - is this correct?
fburner = Param(["f_status", "f_mode"],["integer","integer"],[DEC(NaN),DEC(NaN)]) #TODO Check - is this correct?
monitor = Param(["sys_state"],["integer"],[DEC(NaN)])
params.extend([whburner, fburner, monitor])

scans_accum = Param(["scans_accum"],["integer"],[0]) # cleared every time a record is written
sec_whrun = Param(["sec_whrun"],["integer"],[0]) # total accumulated run time, but output zero at end of 60-sec records
sec_frun = Param(["sec_frun"],["integer"],[0]) # total accumulated run time, but always value of zero at end of 60sec recs
sec_whcooldown = Param(["sec_whcooldown"],["integer"],[0]) # accumulated cool time, set to 0 when in state 5 or 6
sec_fcooldown = Param(["sec_fcooldown"],["integer"],[0]) # accumulated cool time, set to 0 when in state 5 or 6
sec_count = Param(["sec_count"],["integer"],[1]) # divisor to calculate averages over the record period. # of secs since last rec
params.extend([scans_accum, sec_whrun, sec_frun, sec_whcooldown, sec_fcooldown, sec_count])


#####################################################

HeaderRec = 0
UnitsRec = 1
SingleScanRec = 2
MultiScanRec = 3

def record(recType):
    returnString = ""
    for param in params:
        fields = None
        #print("Param(s): {}".format(param.reportHeaders()))
        if (recType == HeaderRec):
            fields = param.reportHeaders()
        elif (recType == UnitsRec):
            fields = param.reportUnits()
        elif (recType == SingleScanRec):
            fields = param.reportScanData()
            # Increment record number integer
            if param.reportHeaders() == ['rec_num']:
                #print("prev_recnum is:{}".format(fields[0]))
                param.setValue(fields[0]+1)
                #print("new recnum value:{}".format(param.reportScanData()))
        elif (recType == MultiScanRec):
            fields = param.reportStatData()
            # Increment record number integer
            if param.reportHeaders() == ['rec_num']:
                #print("prev_recnum is:{}".format(fields[0]))
                param.setValue(fields[0]+1)
                #print("new recnum value:{}".format(param.reportScanData()))
        #print("Fields:{}".format(fields))
        commaIndex = 0
        for field in fields:
            if (param == params[-1]) and (commaIndex == (len(fields)-1)):
                #print("field:{} of fields:{}".format(field,fields), end='\n') #last item
                returnString = returnString+str(field)+'' #rely on filewrite to add own \n
            else:
                #print("{}, ".format(field), end='') #end='\n'
                returnString = returnString+str(field)+','
            commaIndex = commaIndex + 1
    #print("\n-End of record print-")
    return returnString

