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
## 2015-01-22 DanC - Changed dTOff for burner status, dropped conversion of XBee output to volts
## 2015-01-22 DanC - Pressure converted immediately to Pa
## 2015-01.26 DanC - added currentValue to Sensor, (and p_current as Dlvr object ?)
## 2015-01.27 DanC - Changed pressure output (std dev), shortened param headers
## 2015-01.28 DanC - Added statistics, stdev, reduced data precision
## 2015-01.29 DanC - Added new functions to find stats for 60-sec records inclusive of last value (pressure, CO2)
##                 - Added screen for which pressure value is current when closing 60-sec record
## 2015-01.30 DanC - Renamed some Ains, commented some unused fcns
## 2015-01.30 DanC - Record fields 
## 2015.02.01 DanC - Record values of status, modes, state
## 2015.02.02 DanC - Dropped attempts to capture status values from prior scan.  Fixed stddev. 
##                 - Edited burner rules. 
## 2015.02.03 DanC - Pressure single scan values, run time, burner rules
## 2015.02.04 DanC - Edited Burner calcMode() to actively set mode=0 for non-existent appliance, and to set time values to 0 
##                 - Edited Burner status rules temperature values for field deployment rather than bench testing.  
## 2015.02.04 DanC - Edited Burner status rules temperature values to prevent alternating cycles of on & off


from __future__ import print_function
import math, signal, time, gc
from datetime import datetime
import numbers
from decimal import * ## https://docs.python.org/2/library/decimal.html
from smbus import SMBus
import Adafruit_BBIO.GPIO as GPIO
import LoggerConfig as Conf
from statistics import stdev


######################################################
## buses, chips and protocols

## DWC 02.01 moved up from below
def DEC(number):
    return Decimal(number) #"{:d}".format(number)

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
        self.currentVal = DEC(-77)
        pass

    ## DWC 01.26 add a mechanism for capturing current value without appending to list
    def setCurrentVal(self, passedvalue):
        self.currentVal = passedvalue
        pass
        
    def clearValues(self):
        self.values = list()
        pass

    def clearValuesExceptLast(self):
        if len(self.values) <=0:
            self.values = list()
        else:
            lastPop = self.values.pop()
            self.values = list() # make empty set
            self.values.append(lastPop)
            #print("Sensor {} now has values {}".format(self.name, self.values)) ## Debug
        pass

    def appendValue(self, value):
        self.values.append(value)
        pass

    def getLastVal(self):
        return NaN if len(self.values) <= 0 else self.values[-1]

    def getPrevVal(self):
        return NaN if len(self.values) <= 1 else self.values[-2]

    def getValCnt(self):
        return len(self.values)

    def getValCntExceptLast(self):
        return len(self.values)-1

    def getAvgVal(self):  ## NOTE EXCLUDES LAST VALUE CAPTURED
        if len(self.values) <= 0:
            return NaN
        elif len(self.values) == 1:
            return math.fsum(self.values)/len(self.values)
        else:
            clippedValues = list()
            for item in self.values:
                clippedValues.append(item)
            clippedValues.pop() #drop the last item
            return math.fsum(clippedValues)/len(clippedValues)
            
    ## DWC 01.29 Alternative versions of stat functions that include last value captured            
    def getAvgValInclusive(self):  ## NOTE INCLUDES LAST VALUE CAPTURED
        if len(self.values) <= 0:
            return NaN
        else: 
            return math.fsum(self.values)/len(self.values)

    def getMinVal(self):  ## NOTE EXCLUDES LAST VALUE CAPTURED
        if len(self.values) <= 0:
            return NaN 
        elif len(self.values) == 1:
            return min(self.values)
        else: 
            clippedValues = list()
            for item in self.values:
                clippedValues.append(item)
            clippedValues.pop() #drop the last item
            return min(clippedValues)

    def getMinValInclusive(self):  ## NOTE INCLUDES LAST VALUE CAPTURED
        if len(self.values) <= 0:
            return NaN 
        else:
            return min(self.values)

    def getMaxVal(self):  ## NOTE EXCLUDES LAST VALUE CAPTURED
        if len(self.values) <= 0:
            return NaN 
        elif len(self.values) == 1:
            return max(self.values)
        else:
            clippedValues = list()
            for item in self.values:
                clippedValues.append(item)
            clippedValues.pop() #drop the last item
            return max(clippedValues)
    
    def getMaxValInclusive(self):  ## NOTE INCLUDES LAST VALUE CAPTURED
        if len(self.values) <= 0:
            return NaN 
        else:
            return max(self.values)
    
    ## DWC 01.28 implement stdev, carried through to SampledParam
    ## DWC 01.28 Not working, temporarily replace stdev with min 
    def getStdDev(self):  ## NOTE EXCLUDES LAST VALUE CAPTURED
        if len(self.values) <= 2:
            return NaN
        else:
            clippedValues = list()
            for item in self.values:
                clippedValues.append(item)
            clippedValues.pop() #drop the last item
            #ss = 0
            #mean = 2
            #for x in (clippedValues):
            #    ss = ss + x**2.0   ## cast as float?
            #standard_dev = math.sqrt(ss/len(clippedValues))
            return stdev(clippedValues)
        #print("stdev exclusive error")            

    def getStdDevInclusive(self):  ## NOTE INCLUDES LAST VALUE CAPTURED
        if len(self.values) <= 2:
            return NaN
        else:
            #ss = 0
            #for x in (self.values):
            #    ss = ss + x**2.0   ## cast as float?
            #standard_dev = stdev(self.values)
            return stdev(self.values)
        #print("stdev inclusive error")
        
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
  BurnerTc("TC01@U11", Adc.U11, Adc.MUX0),
        Tc("TC02@U11", Adc.U11, Adc.MUX1),
        Tc("TC03@U11", Adc.U11, Adc.MUX2),
        Tc("TC04@U11", Adc.U11, Adc.MUX3),

        Tc("TC05@U13", Adc.U13, Adc.MUX0),
        Tc("TC06@U13", Adc.U13, Adc.MUX1),
  BurnerTc("TC07@U13", Adc.U13, Adc.MUX2),
        Tc("TC08@U13", Adc.U13, Adc.MUX3),

        Tc("TC09@U14",  Adc.U14, Adc.MUX0),
        Tc("TC10@U14", Adc.U14, Adc.MUX1),
        Tc("TC11@U14", Adc.U14, Adc.MUX2),
        Tc("TC12@U14", Adc.U14, Adc.MUX3),

        Tc("TC13@U15", Adc.U15, Adc.MUX0),
        Tc("TC14@U15", Adc.U15, Adc.MUX1),
        Tc("TC15@U15", Adc.U15, Adc.MUX2), ## outdoor temp sensor
        Tc("TC16@U15", Adc.U15, Adc.MUX3), ## spare tc
    ]

ains.extend(tcs)

class CO(Ain):
    """includes all (ADC-attached) CO sensor inputs"""
    def __init__(self, name, adcIndex, mux, pga=PGA, sps=SPS, co_calib_value=1700):
        Ain.__init__(self, name, adcIndex, mux, pga=PGA, sps=SPS)
        try:
            self.co_calib_value = Conf.co_calib_value  #try to base it off Configuration File first
        except:
            self.co_calib_value = co_calib_value #otherwise, go with what's written in above
        pass
    
    def appendAdcValue(self, value):
        value = value
        volts = value/1000  ## get this converted to engineering units, and test 
        result = ((volts * 0.5) * 2.326e6) / self.co_calib_value
        self.appendValue(result)
        pass


#door1 = Ain("JP1-A@U8", Adc.U8, Adc.MUX0) ## door1 pose
#fan1 = Ain("JP1-B@U8", Adc.U8, Adc.MUX1) ## fan current 1 sensor
#fan2 = Ain("JP1-C@U8", Adc.U8, Adc.MUX2) ## fan current 2 sensor
#co   = CO("JP1-D@U8", Adc.U8, Adc.MUX3) ## CO sensor
## Old names above
## Try changing names to make them easier to search on later
door1 = Ain("DOOR-A@U8", Adc.U8, Adc.MUX0) ## door1 pose
fan1 = Ain("AIN-B@U8", Adc.U8, Adc.MUX1) ## fan current 1 sensor
fan2 = Ain("AIN-C@U8", Adc.U8, Adc.MUX2) ## fan current 2 sensor
co   = CO("CO-D@U8", Adc.U8, Adc.MUX3) ## CO sensor
ains.extend([door1, fan1, fan2, co]) ## remaining ains NOT included: [co2..., niu1, niu2, batt, niu3, niu4, niu5, niu6])
 

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

    ## Not used
    #def setValves(self):
    #    ## sets all valves as appropriate for sampling this co2 sensor's nominal location
    #    ## --should be called as early as possible before the adc
    #    for valve in range(len(co2_valves)): ##[CO2.valve_whvent, CO2.valve_fvent, CO2.valve_zone]: ## set the valves per the ctor arg
    #        co2_valves[valve].setValue(valve == self.valve)
    #    co2_valve_pos.setValue(self.valve) ## set the ad hoc param value for reporting valve position
    #    co2_valve_time.setValue(now()) ## set the ad hoc param value for reporting valve open time--TODO should be elapsed time

    def appendAdcValue(self, value):
        #value = value
        ## move conversion to fetchAdc, so values are in engr units if used or viewed in loop before append is executed
        #volts = value/1000
        #ppmCO2 = 2000 * volts   ## get this converted to engineering units (PPM)
        self.appendValue(value)
        pass

co2_whvent = CO2("J25-1@U9a", Adc.U9, Adc.MUX0, CO2.valve_whvent) ## valve-switched--unique CO2 sensor on same ADC
co2_fvent = CO2("J25-1@U9b", Adc.U9, Adc.MUX0, CO2.valve_fvent) ## valve-switched--unique CO2 sensor on same ADC
co2_zone  = CO2("J25-1@U9c", Adc.U9, Adc.MUX0, CO2.valve_zone) ## valve-switched--unique CO2 sensor on same ADC
co2_sensors = [co2_whvent, co2_fvent, co2_zone]
ains.extend(co2_sensors)

niu1 = Ain("J25-2@U9", Adc.U9, Adc.MUX1) ## unused ain
niu2 = Ain("J25-3@U9", Adc.U9, Adc.MUX2) ## unused ain
batt = Ain("J25-4@U9", Adc.U9, Adc.MUX3) ## battery voltage sensor

niu3 = Ain("J25-5@U10", Adc.U10, Adc.MUX0) ## spare ain
niu4 = Ain("J25-6@U10", Adc.U10, Adc.MUX1) ## spare ain
niu5 = Ain("J25-7@U10", Adc.U10, Adc.MUX2) ## spare ain
niu6 = Ain("J25-8@U10", Adc.U10, Adc.MUX3) ## spare ain

sensors.extend(ains)
## DWC 12.14 need ain.extend and sensors.extend for these: [co2..., niu1, niu2, batt, niu3, niu4, niu5, niu6]

class Dlvr(I2c, Sensor):
    """includes the (I2C-attached) DLVR pressure sensor input"""

    valve_zero = 0 ## 1
    valve_whvent = 1 ## 2
    valve_fvent = 2 ## 3
    valve_zone = 3 ## 4
    valve_current = 9 ## Not used to set valves, p_current just used to capture new pressure before assignment to loc-specific parameter
    
    def __init__(self, name, i2cIndex, valve):
        I2c.__init__(self, name, i2cIndex, addr=0x28)
        Sensor.__init__(self, name)
        self.valve = valve
        pass
    
    ## not used
    #def setValves(self):
    #    ## sets all valves as appropriate for sampling this pressure sensor's nominal location
    #    ## --should be called as early as possible before the reading?
    #    for valve in range(len(p_valves)): ##[Dlvr.valve_zero, Dlvr.valve_whvent, Dlvr.valve_fvent, Dlvr.valve_zone]: ## set the valves per the ctor arg
    #        p_valves[valve].setValue(valve == self.valve)
    #    p_valve_pos.setValue(self.valve) ## set the ad hoc param value for reporting valve position
    #    p_valve_time.setValue(now()) ## set the ad hoc param value for reporting valve open time--TODO should be elapsed time

    def readPressure(self):
        Response = self.readList(reg=0,length=4)
        Status = (Response[0]>>6) & 0xFF
        #print "Status bits are (in binary): ", format(Status,'02b')
        if Status != 0:
            # print("Pressure Data not Ready!")  
            return float('NaN')
        else:
            #Extract Pressure Value:
            Pressure = (((Response[0]<<2)>>2)<<8) + Response[1]
            #print "Pressure output is (in binary): ",format(Pressure,'014b')
            #print "Pressure output is (in hex): ",format(Pressure,'04x')
            #print "Pressure output is (in dec): ",Pressure
            #Calculate Pressure:
            ## DWC 01.25 corrected for 1 inch differential sensor used in final design
            Pressure_inH20 = 1.25*((float(Pressure)-8192)/(2**14))*2 
            Pressure_Pa = Pressure_inH20*248.84  ## Conversion from ASHRAE
            #print "Pressure, converted is: ",format(Pressure_inH20,'0.6f'),"inH20"
            #Extract Temp Value:
            #Temp = (Response[2]<<3)+(Response[3]>>5)
            #print "Temperature output is (in binary): ", format(Temp,'011b')
            #print "Temperature output is (in dec): ",Tem
            #Temp_C = (float(Temp)*(float(200)/(2047)))-50
            #print "Temp, converted is: ",Temp_C,"deg. C"
            return Pressure_Pa
        pass
    
    ## No need for new append, can use std Sensor class append        
    """
    def appendAdcValue(self, value):
        #value = value #should come in as in_H20
        #resultPascals = Decimal(value)/Decimal(0.00401463078662)  ## converted to Pascals
        #self.appendValue(resultPascals)
        ## DWC 01.25 simplified, values should already be in Pa
        self.appendValue(value)
        pass
    """
    
    ## DWC 01.26 don't appear to need this, can use Sensor.setCurrentVal()
    #def assignPressValue(self, value)
        #pass


p_zero    = Dlvr("DLVR@U12", I2c.I2C1, Dlvr.valve_zero)
p_whvent  = Dlvr("DLVR@U12", I2c.I2C1, Dlvr.valve_whvent)
p_fvent   = Dlvr("DLVR@U12", I2c.I2C1, Dlvr.valve_fvent)
p_zone    = Dlvr("DLVR@U12", I2c.I2C1, Dlvr.valve_zone)
p_current = Dlvr("DLVR@U12", I2c.I2C1, Dlvr.valve_current)
p_sensors = [p_zero, p_whvent, p_fvent, p_zone]  ## Don't include p_current in list

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
        ## DWC 01.22 drop conversion to volts - raw value convenient, offers insight on resolution steps when fan is on
        ## Should probably re-name it other than volts
        volts = value #*0.001173 # per xbee adc conversion to volts
        #volts = value*0.001173 # per xbee adc conversion to volts
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
        ## **** EDIT VALUES BEFORE FIELD DEPLOYMENT
        T_ON_THRESHOLD  = 250       ## Avg temp above this values -> burner ON  02.17 changed 190 to 250 to prevent cycling on cooling
        T_OFF_DEADBAND  =  50       ## Avg temp below  (T_ON_THRESHOLD - this value) -> burner OFF.  02.17 changed 30 to 50
        #DT_TURN_ON     =   5       ## Set in waterHtr and furnace intialization below, so can be adjusted to different values if needed
        #DT_TURN_OFF    =  -5       ## Set in waterHtr and furnace intialization below, so can be adjusted to different values if needed
        DT_STAY_ON      =   8       ## Temp rise rate to confirm On status - changed from 10 to 8, but may not be needed 
        DT_STAY_OFF     =  -5       ## Temp drop rate to confirm Off status - changed from -10 to-5 due to cycling

        self.prevStatus  = self.status
        last = self.tc.getLastVal()
        if (last != NaN):
            avg = self.tc.getMovAvg()
            if (self.prevStatus == self.STATUS_OFF):       ## Previous status is OFF   
                if ((last - avg) <  DT_STAY_OFF):     ## Steep temp decline, prevents considering absolute temp
                    self.status = Burner.STATUS_OFF    
                elif ((last - avg) > self.dtOn):
                    self.status = Burner.STATUS_ON
                elif (avg > T_ON_THRESHOLD):          ## Absolute temp test
                     self.status = Burner.STATUS_ON
                else:
                    pass    ## Hold status OFF 
            else:                            ## Previous status is ON
                if ((last - avg) >  DT_STAY_ON):       ## Steep temp rise, prevents considering absolute temp as long as temp is in steep rise
                    self.status = Burner.STATUS_ON
                elif ((last - avg) < self.dtOff):
                    self.status = Burner.STATUS_OFF
                elif (avg < (T_ON_THRESHOLD - T_OFF_DEADBAND)):    ## Absolute temp test
                     self.status = Burner.STATUS_OFF
                else:
                    pass    ## Hold status ON 
            #else no change
        return self.status

    def getStatus(self):
        return self.status

    ## DWC 12.14 Major revision
    def calcMode(self):
        """N.B. this method also sets the stopTime which is used in the calculation--must be called once and only once every tick"""
        ## self.mode = Burner.Mode0NotPresent  Why would this be here - covered in initialization
        if (self.isPresent):
            self.prevMode = self.mode     ## Moved up from end
            self.calcStatus() ## update status
            self.timeOn = 0  ## set in mode calcs as needed.  02.03 set as integer, not 0.0
            self.timeCooling = 0
            ## DWC 12.14 drop: self.mode = Burner.Mode2On if (self.status == Burner.STATUS_ON) else Burner.Mode5Off
            ## DWC 12.14 don't think we need this if values are intialized:
            #if (self.prevMode is not None):
            if (self.prevMode == Burner.Mode1JustStarted):
                if (self.status == Burner.STATUS_ON):
                    self.mode = Burner.Mode2On
                    self.timeOn = math.trunc(now()) - self.startTime #use now()??
                else:
                    self.mode = Burner.Mode4Cooling
                    ## unexpected--register an error
                    self.stopTime = math.trunc(now())
            elif (self.prevMode == Burner.Mode2On):
                if (self.status == Burner.STATUS_OFF):
                    self.mode = Burner.Mode3JustStopped
                    self.timeOn = math.trunc(now()) - self.startTime
                    self.stopTime = math.trunc(now())
                else:
                    self.timeOn = math.trunc(now()) - self.startTime
                    ## no change in mode
            elif (self.prevMode == Burner.Mode3JustStopped):
                if (self.status == Burner.STATUS_OFF):
                    self.mode = Burner.Mode4Cooling
                    self.timeCooling = math.trunc(now()) - self.stopTime
                else:
                    self.mode = Burner.Mode1JustStarted
                    ## unexpected--register an error
                    self.startTime = math.trunc(now()-1)  ## DWC 02.03 start burner timer at 1, rather than 0
                    self.timeOn = math.trunc(now()) - self.startTime  ## And accumulate run time on burner start
            elif (self.prevMode == Burner.Mode4Cooling):
                if (self.status == Burner.STATUS_OFF):
                    self.timeCooling =math.trunc(now()) - self.stopTime
                    ## elapsed = math.trunc(now() - self.stopTime)  Need math.trunc??
                    if (((self.timeCooling >= 120) and ((math.trunc(now()) % 60) == 0))\
                    or (self.timeCooling >= 180) or (self.timeCooling <= -10)):  ## Check for large negative error
                        self.mode = Burner.Mode5Off
                    ## Else stay in Mode4Cooling
                else:
                    self.mode = Burner.Mode1JustStarted
                    self.startTime = math.trunc(now()-1)
                    self.timeOn = math.trunc(now()) - self.startTime
            elif (self.prevMode == Burner.Mode5Off):
                if (self.status == Burner.STATUS_ON):
                    self.mode = Burner.Mode1JustStarted
                    self.startTime = math.trunc(now()-1)
                    self.timeOn = math.trunc(now()) - self.startTime
                ## Else stay in Mode5Off
        else:
            ## DWC 02.04 added mode setting for non-present appliance, and time values (always 0 sec) to be availablein Main
            self.mode = Burner.Mode0NotPresent            
            self.prevMode = Burner.Mode0NotPresent
            self.timeOn = 0  ## set in mode calcs as needed.  02.03 set as integer, not 0.0
            self.timeCooling = 0
        return self.mode

    def getMode(self):
        return self.mode

waterHeaterIsPresent = (Conf.waterHeaterIsPresent is not None and Conf.waterHeaterIsPresent == True)
furnaceIsPresent = (Conf.furnaceIsPresent is not None and Conf.furnaceIsPresent == True)

## Set dTemps for identifying burner turn on and turn off in constructors
waterHtr = Burner("waterHtr", 5, -5, 0, waterHeaterIsPresent)  ## DWC 01.22 changed both dT Off tests to -5F
furnace = Burner("furnace", 5, -5, 6, furnaceIsPresent)
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

currentPressureValveGlobal = -1  ## initialize with meaningless value

## DWC 01.29 Define new values to capture pressure valve number and CO2 valve number globally
def setCurrentPressureValve(valvenum):
    currentPressureValveGlobal = valvenum
    pass 

def getCurrentPressureValve():
    return currentPressureValveGlobal
    
            

def TIME(tm):
    return time.strftime("\"%Y-%m-%d %H:%M:%S\"",time.gmtime(tm))

class Param(object):
    """includes all parameters to be reported"""

    def __init__(self, headers, units=[""], values=[""]):
        self.headers = headers
        self.units = units
        self.values = values
        #self.savedValue  ## List because it must be iterable in record()

    def reportHeaders(self):
        return self.headers

    def reportUnits(self):
        return self.units ## len must match headers

    def reportScanData(self): ## len must match headers and units
        return self.values

    def reportStatData(self): ## len must match headers and units
        return self.values

    ## DWC 02.02 drop attempts to save status values from top of scan
#    def reportSavedStatData(self): ## len must match headers and units
#        return self.savedValue
#
#    ## DWC 0201 new functions to save timestamp for start of record, and state from prior scan
#    def setSavedVal(self, passed_value):
#        self.savedValue = passed_value
#        
#    ## Not sure we need this, may just use reportSavedStatData()  
#    ## Returns a list, because it must be iterable later in record()
#    def getSavedVal(self):
#        return [self.savedValue]       

    ## DWC 01.25 Is this append correct?  <= 0 looks funny
    ## It appears to be used in record setup: param.setValue(fields[0]+1)
    def setValue(self, value): ## storage for ad hoc params
        if (len(self.values) <= 0): 
            self.values.append(value)
        else: 
            self.values[0] = value
 
siteid = Param(["site"], [""], [Conf.siteName])
timestamp = Param(["time"], ["UTC"], [TIME(Timer.stime())])  ## DWC 02.01 changed name from timest
recnum = Param(["rec_num"],["integer"],[0])

params = [siteid, timestamp, recnum] ## alnum, utc, int
diagParams = [timestamp,siteid] ## set for diagnostic file's parameters

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

    ## DWC 01.27 TODO ***
    ## DWC 01.27 add alternate alt_setval for use with pressure and CO2, where param values are set conditionally on passing of clearance time
    #def alt_setval(passedvalue)
    #    self.alt

    def avgVal(self):
        return DEC(self.sensor.getAvgVal())

    def avgValInclusive(self):
        return DEC(self.sensor.getAvgValInclusive())

    def minVal(self):
        return DEC(self.sensor.getMinVal())

    def minValInclusive(self):
        return DEC(self.sensor.getMinValInclusive())

    def maxVal(self):
        return DEC(self.sensor.getMaxVal())

    def maxValInclusive(self):
        return DEC(self.sensor.getMaxValInclusive())

    def stdDev(self):
        return DEC(self.sensor.getStdDev())

    def stdDevInclusive(self):
        return DEC(self.sensor.getStdDevInclusive())

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
        
## DWC 01.27 shortened header designations to allow higher data display density
t_whburner = TempParam("t_whbrn", tcs[0])
t_whspill1 = TempParam("t_whsp1", tcs[1])
t_whspill2 = TempParam("t_whsp2", tcs[2])
t_whspill3 = TempParam("t_whsp3", tcs[3])
t_whspill4 = TempParam("t_whsp4", tcs[4])
t_whvent = TempParam("t_whvnt", tcs[5])
params.extend([t_whburner, t_whspill1, t_whspill2, t_whspill3, t_whspill4, t_whvent])

t_fburner = TempParam("t_fbrn", tcs[6])
t_fspill1 = TempParam("t_fsp1", tcs[7])
t_fspill2 = TempParam("t_fsp2", tcs[8])
t_fspill3 = TempParam("t_fsp3", tcs[9])
t_fspill4 = TempParam("t_fsp4", tcs[10])
t_fvent = TempParam("t_fvnt", tcs[11])
params.extend([t_fburner, t_fspill1, t_fspill2, t_fspill3, t_fspill4, t_fvent])

t_zonehi = TempParam("t_zonhi", tcs[12])
t_zonelow = TempParam("t_zonlow", tcs[13])
t_outdoor = TempParam("t_out", tcs[14])
t_extra = TempParam("t_xtra", tcs[15])
params.extend([t_zonehi, t_zonelow, t_outdoor, t_extra])

class AinParam(SampledParam):
    """includes all AIN (sampled) parameters"""
    def __init__(self, loc, sensor):
        SampledParam.__init__(self, [loc+"", loc+"_min", loc+"_max"], ["V", "V", "V"], loc, sensor) 

pos_door1 = AinParam("pos_dr1", door1) ## TODO
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
    global currentPressureValveGlobal
    ## DWC 01.27 reduce to avg, range, and std dev for accumulated values
    def __init__(self, loc, sensor):
        fix = "p_"+loc
        SampledParam.__init__(self, [fix+"", fix+"_rng", fix+"_stdev"], ["Pa", "Pa", "Pa"], loc, sensor) 

    def reportScanData(self): ## override
        ## DWC 02.03 set current val for range and stddev positions to NaN, since they don't represent real values of either
        return [self.val(), NaN, NaN]
        #return [self.val(), self.val(), self.val()]
 
    def reportStatData(self): ## override using currentPressureValveGlobal to determine when last value is used
        if True:       # currentPressureValveGlobal == 1:
            ## Use min max for testing, then go to stddev
            #return [self.avgVal(), self.minVal(), self.maxVal()]
            return [self.avgVal(), (self.maxVal()-self.minVal()), self.stdDev()]

    ## DWC 01.29 add new fcn that does not drop last value
    def reportStatDataInclusive(self): ## override using currentPressureValveGlobal to determine when last value is used
            ##  Use min max for testing, then go to stddev
            return [self.avgValInclusive(), (self.maxValInclusive()-self.minValInclusive()), self.stdDevInclusive()]


p_valve_pos = Param(["loc_p"],["integer"],[DEC(NaN)]) ## ad hoc param for reporting pressure valve position
p_valve_time = Param(["sec_p"],["integer"],[0]) ## ad hoc param for reporting pressure valve open time
zeropress = PressureParam("zero", p_zero) 
whventpress = PressureParam("whvent", p_whvent)
fventpress = PressureParam("fvent", p_fvent)
zonepress = PressureParam("zone", p_zone)
params.extend([p_valve_pos, p_valve_time, zeropress, whventpress, fventpress, zonepress])

## DWC 02.01 intitialize to default values, rather than DEC(NaN)
## DWC 02.02 drop the DEC)0) in initialization
whburner_stat = Param(["wh_status"],["integer"],[0])
whburner_mode = Param(["wh_mode"],["integer"],[5]) 
fburner_stat = Param(["f_status"],["integer"],[0]) 
fburner_mode = Param(["f_mode"],["integer"],[(5)])
monitor = Param(["sys_state"],["integer"],[6])
params.extend([whburner_stat,whburner_mode,fburner_stat, fburner_mode, monitor])

scans_accum = Param(["scans_accum"],["integer"],[0]) # cleared every time a record is written
sec_whrun = Param(["sec_whrun"],["integer"],[0]) # total accumulated run time, but output zero at end of 60-sec records
sec_frun = Param(["sec_frun"],["integer"],[0]) # total accumulated run time, but always value of zero at end of 60sec recs
sec_whcooldown = Param(["sec_whcool"],["integer"],[0]) # accumulated cool time, set to 0 when in state 5 or 6
sec_fcooldown = Param(["sec_fcool"],["integer"],[0]) # accumulated cool time, set to 0 when in state 5 or 6
sec_count = Param(["sec_count"],["integer"],[1]) # divisor to calculate averages over the record period. # of secs since last rec
params.extend([scans_accum, sec_whrun, sec_frun, sec_whcooldown, sec_fcooldown, sec_count])


class XbeeParam(SampledParam):
    def __init__(self, loc, sensor):
        fix = loc
        SampledParam.__init__(self, [fix+""], ["V"], loc, sensor) 

    def reportScanData(self): ## override
        return [self.val()]

    def reportStatData(self): ## override
        return [self.avgVal()]

#####################################################

HeaderRec = 0
UnitsRec = 1
SingleScanRec = 2
MultiScanRec = 3

def record(recType):
    returnString = ""
    for param in params:
        fields = None
        trimmedFields = list() #empty list
        #print("Param(s): {}".format(param.reportHeaders()))
        if (recType == HeaderRec):
            fields = param.reportHeaders()
            #print("HEADERS: {}".format(fields))
        elif (recType == UnitsRec):
            fields = param.reportUnits()
        elif (recType == SingleScanRec):
            fields = param.reportScanData()
            #print("Fields before:{}".format(fields))
            ## Increment record number integer
            if param.reportHeaders() == ['rec_num']:
                #print("prev_recnum is:{}".format(fields[0]))
                param.setValue(fields[0]+1)
                #print("new recnum value:{}".format(param.reportScanData()))
            for field in fields: ## convert precisions
                #print("Param.reportHeaders()[0]: {}".format(param.reportHeaders()[0][0:2])) #DEBUG
                if param.reportHeaders()[0][0:2] == 't_':  #if temps
                    trimmedFields.append(str.format("{:.1f}",field))
                    #print("type Temp. Value: {}".format(trimmedFields[-1]))
                elif  param.reportHeaders()[0][0:3] == 'pos': 
                    trimmedFields.append(str.format("{:.0f}",field))
                elif  param.reportHeaders()[0][0:3] == 'ppm': 
                    trimmedFields.append(str.format("{:.0f}",field))
                #elif  param.reportHeaders()[0][0:7] == 'p_': 
                #    trimmedFields.append(str.format("{:.1f}",field))
                ## v applies to all XBee analog readings    
                elif  param.reportHeaders()[0][0:1] == 'v': 
                    trimmedFields.append(str.format("{:.0f}",field))
                elif  param.reportHeaders()[0][0:3] == 'sec':           ## seconds run time should be integers
                    trimmedFields.append(str.format("{:.0f}",field))
                
                elif isinstance(field,int): 
                    trimmedFields.append(field)
                elif isinstance(field, numbers.Number): #it's still a number
                    trimmedFields.append(str.format("{:.2f}",field))
                else:
                    trimmedFields.append(field)
            fields = list(trimmedFields) # replace with trimmed values
            #print("SINGLE-SCAN FIELDS: {} " .format(fields))
        elif (recType == MultiScanRec):
            ## 0131A DWC need temp variable to get headers for further evaluation?  Should be able to use param
            fields = param.reportStatData()
            ## Capture time stamp from start of record
            #  0131A Can't ref fields here - added fields back above
            if param.reportHeaders() == ['rec_num']:
                #print("prev_recnum is:{}".format(fields[0]))
                param.setValue(fields[0]+1)
                #recnum.setValue(tempfield[0]+1)
                #print("new recnum value:{}".format(param.reportScanData()))
            
            ## does getCurrentPressureValve() work?
            if param.reportHeaders()[0][0:2] == "p_": 
                if  (param.sensor.valve == getCurrentPressureValve()):
                    fields = param.reportStatData()
                else: 
                    fields = param.reportStatDataInclusive()
            ## DWC 02.02 it appears this elif is called in all cases - not sure why
            elif (param.reportHeaders()[0][0:8] == "J25-1@U9"):
                fields = param.reportStatDataInclusive()

            ## DW 02.02 drop attempt to capture saved values from before state setting, etc            
            #elif (param.reportHeaders()[0][0:4] == "time"):    ## reportSavedStatData()
            #    fields = param.reportSavedStatData()
            #elif (param.reportHeaders()[0][0:9] == "wh_status"):
            #    fields = param.reportSavedStatData()
            #elif (param.reportHeaders()[0][0:7] == "wh_mode"):
            #    fields = param.reportSavedStatData()
            #elif (param.reportHeaders()[0][0:8] == "f_status"):
            #    fields = param.reportSavedStatData()
            #elif (param.reportHeaders()[0][0:6] == "f_mode"):
            #    fields = param.reportSavedStatData()
            #elif (param.reportHeaders()[0][0:9] == "sys_state"):
            #    fields = param.reportSavedStatData()
            #elif (param.reportHeaders()[0][0:2] == "WXYZ"):
            #    fields = param.reportSavedStatData()
            #    print("WXYZ  {} " .format(monitor), end='')
            

                # def setSavedVal(self, passed_value):
                # SET timestamp = Param(["time"], ["UTC"], [TIME(Timer.stime())])
                # OK recnum = Param(["rec_num"],["integer"],[0])
                
                # SET whburner_stat = Param(["wh_status"],["integer"],[DEC(NaN)])
                # SET whburner_mode = Param(["wh_mode"],["integer"],[DEC(NaN)]) 
                # SET fburner_stat = Param(["f_status"],["integer"],[DEC(NaN)]) 
                # SET fburner_mode = Param(["f_mode"],["integer"],[DEC(NaN)])
                # SET monitor = Param(["sys_state"],["integer"],[DEC(NaN)])
                #params.extend([whburner_stat,whburner_mode,fburner_stat, fburner_mode, monitor])

                #scans_accum = Param(["scans_accum"],["integer"],[0]) # cleared every time a record is written
                #sec_whrun = Param(["sec_whrun"],["integer"],[0]) # total accumulated run time, but output zero at end of 60-sec records
                #sec_frun = Param(["sec_frun"],["integer"],[0]) # total accumulated run time, but always value of zero at end of 60sec recs
                #sec_whcooldown = Param(["sec_whcool"],["integer"],[0]) # accumulated cool time, set to 0 when in state 5 or 6
                #sec_fcooldown = Param(["sec_fcool"],["integer"],[0]) # accumulated cool time, set to 0 when in state 5 or 6
                #sec_count = Param(["sec_count"],["integer"],[1]) # divisor to calculate averages over the record period. # of secs since last rec
                #params.extend([scans_accum, sec_whrun, sec_frun, sec_whcooldown, sec_fcooldown, sec_count])                                                        
            else:
                ## DWC 01.31 this not needed; override above as needed
                fields = param.reportStatData() 
                pass   
            #print("Fields before:{}".format(fields))
            
            ## As it was, triggers error Type int is not iterable.
            #for field in fields: ## convert precisions  ## TODO is this for loop needed, since we're already cycling through params?
            #    #print("Param.reportHeaders()[0]: {}".format(param.reportHeaders()[0][0:2])) #DEBUG
            #    if param.reportHeaders()[0][0:2] == 't_':  #if temps
            #        trimmedFields.append(str.format("{:.1f}",field))
            #        #print("type Temp. Value: {}".format(trimmedFields[-1]))
            #    elif isinstance(field,int): 
            #        trimmedFields.append(field)
            #    elif isinstance(field, numbers.Number): #it's still a number
            #        trimmedFields.append(str.format("{:.2f}",field))
            #    else:
            #        trimmedFields.append(field)
            #fields = list(trimmedFields) # replace with trimmed values
            
            #print("MULTI-SCAN FIELDS: {} " .format(fields))
            for field in fields: ## convert precisions  ## TODO is this for loop needed, since we're already cycling through params?
                #print("Param.reportHeaders()[0]: {}".format(param.reportHeaders()[0][0:2])) #DEBUG
                #try:
                    if param.reportHeaders()[0][0:2] == 't_':  #if temps
                        trimmedFields.append(str.format("{:.1f}",field))
                        #print("type Temp. Value: {}".format(trimmedFields[-1]))
                #except:
                #    print("Failed at  if param.reportHeaders()")
                #try:
                    ## ppm applies to both CO and CO2
                    elif  param.reportHeaders()[0][0:3] == 'pos': 
                        trimmedFields.append(str.format("{:.0f}",field))
                    elif  param.reportHeaders()[0][0:3] == 'ppm': 
                        trimmedFields.append(str.format("{:.0f}",field))
                    #elif  param.reportHeaders()[0][0:7] == 'p_': 
                    #    trimmedFields.append(str.format("{:.1f}",field))
                    ## v applies to all XBee analog readings    
                    elif  param.reportHeaders()[0][0:1] == 'v': 
                        trimmedFields.append(str.format("{:.0f}",field))
                    elif  param.reportHeaders()[0][0:3] == 'sec':           ## seconds run time should be integers
                        trimmedFields.append(str.format("{:.0f}",field))                    
                    
                    elif isinstance(field,int): 
                        trimmedFields.append(field)
                    elif isinstance(field, numbers.Number): #it's still a number
                        trimmedFields.append(str.format("{:.2f}",field))
                    else:
                        trimmedFields.append(field)
                    #print("TRIMMED FIELDS: {} " .format(trimmedFields))    
                #except:
                #    print("Failed at isinstance lines")
                    
            fields = list(trimmedFields) # replace with trimmed values
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

def diag_record(recType):
    returnString = ""
    for param in diagParams:
        fields = None
        #print("Param(s): {}".format(param.reportHeaders()))
        if (recType == HeaderRec):
            fields = param.reportHeaders()
        elif (recType == UnitsRec):
            fields = param.reportUnits()
        elif (recType == SingleScanRec):
            fields = param.reportScanData()
        elif (recType == MultiScanRec):
            fields = param.reportStatData()
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


