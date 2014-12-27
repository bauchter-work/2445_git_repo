#! /usr/bin/python

## LoggerMain -- Combustion Monitoring logic
##
## 2014-11-05 TimC - Initial
## 2014-11-16 TimC - moved setups to library; 
## 2014-11-17 TimC - first cut at state selection logic
## 2014-11-18 TimC - changed mon.state to property, added prevState; cleanup state selection; added example gpio get
## 2014-11-20 BenA - sidestepping some issues with the ADC library for now; using Adafruit library until understood
## 2014-11-24 BenA - added watchdog, config file query, uniqueID, gpio setup, pressure read
## 2014-11-30 DanC - added material related to record control and fetching data values
## 2014-11-30 TimC - accomodate new i2c exceptions; remove random; init burners as off
## 2014-12-08 BenA - added xbee data input - assuming up to three xbee nodes
## 2014-12-09 TimC - accomodate new lib method signatures
## 2014-12-12 TimC - move setting of furnace and waterhtr tcs to library; accommodate some revisions in lib; call the improved burner mode calc methods; implement Dan's state determination logic
## 2014.12.14 DanC - drop Adafruit adc call, try fixing adc call using Tim's library
## 2014.12.16 DanC - made some changes to state controller, add import datetime, change screen print
##                 - added from __future__ import print, changed all old print statements to print()
##                 - added control of pressure and CO2 valves 
## 2014.12.27 DanC - rearranged print statements to show output on one line only, starting with time (sec into GMT day)
## 
 
from __future__ import print_function

import time, math, sys, os
from datetime import datetime
from decimal import *
import LoggerLib as Lib
from Adafruit_ADS1x15_mod import ADS1x15 
import Adafruit_BBIO.UART as UART
from xbee import zigbee
import serial


##########################################################################################
## Constants 
CO2VALVECYCLE = 20   ## CO2 valve operating cycle (sec)
CO2CLEARTIME  = 10   ## Time allowed for clearing CO2 system, good data comes after this
PRESSVALVECYCLE = 3
NaN = float('NaN')

#Record keeping
HEADER_REC = 0
UNITS_REC = 1
SINGLE_SCAN_REC = 2
MULTI_SCAN_REC = 3

###########################################################################################
## setup / initialize

## Activate watchdog
try:
    watchdog = open("/dev/watchdog",'w+')
    watchdog.write("\n")
except:
    print("Unable to access watchdog")

## Get UniqueID for BBB
try:
    os.system("/root/field-code/getUniqueID.sh") #run this to extract Serial Number for EEPROM
    uniqueFile = open("uniqueID",'r')
    uniqueID = uniqueFile.readline().rstrip('\n')
    #print "BBB unique ID is {}".format(uniqueID)
except:
    print("Error retrieving UniqueID from BBB EEPROM")

## Load Configuration File
try: 
    import LoggerConfig as Conf

except:
    print("No LoggerConfig.py file available or error parsing")
    sys.exit()

## setup all General Purpose Inputs and Outputs
for control in Lib.controls:
    control.setValue(0) #write GPIO.LOW
#print("GPI {}: reads {}".format(Lib.sw1.name,Lib.sw1.getValue() ))
#print("GPI {}: reads {}".format(Lib.sw2.name,Lib.sw1.getValue() ))

## Turn on 24V power
for control in Lib.controls:
    if control.name == "24V@P8-15":
        control.setValue(1) #write GPIO.HIGH

## Setup zigbee UART for asynchronous operation
UART.setup("UART4")
ser = serial.Serial(port="/dev/ttyO4",baudrate=9600, timeout=1) #this is a letter "Oh"-4

ADS1115=0x01 # Defined for Adafruit ADC Library 

###########################################################################################
## local functions
# ==============================================================================

def get_free_space_bytes(folder):
    #command to check remaining free space on the storage device
    st = os.statvfs(folder)
    return st.f_bavail * st.f_frsize
    pass

def fetchXbee(data):
    try:
        print("Xbee data Received")
        for sensor in Lib.sensors:
            if isinstance(sensor, Lib.Xbee):
                matchAddress = False
                for item in data:
                    #print "item is",str(item)
                    if (str(item) == 'source_addr_long'):
                        #print '\t'+str(item),data[item].encode("hex")[12:16]
                        #print "addr_long is:",str(data[item].encode("hex")[12:16])
                        if ("0x"+str(data[item].encode("hex")[12:16])) == sensor.address:
                            matchAddress = True
                            #print "\tThere is a match",sensor.address
                    elif str(item) == 'samples':
                        samplesDict = data[item]
                        for x in samplesDict:
                            for y in x: 
                                if matchAddress and str(y) == str(sensor.adc):
                                    #print '\t'+str(y),x[y]*0.001173,"volts",sensor.adc 
                                    sensor.appendAdcValue(x[y]) # convert and record into volts
    except:
        print ("unable to print or parse xbee data")
    pass


def fetchTempsAdafruit(ADCs): #TODO remove this function once fetchTemps() is verified sound
    for mux in range(4):
        for job in range(2): ##[Start, fetch]
            for ADC in ADCs:
              if (job ==0): #start
                Value=ADC.readADCSingleEnded(mux,1024,250)
              else:
                Value=ADC.readADCSingleEnded(mux,1024,250)
                Volts = Value/1000
                #print("adafruitLib ADC 0x{:02x} measures:{} , AIN:{}".format(ADC.address,Volts,mux))
                for sensor in Lib.sensors:
                    if isinstance(sensor,Lib.Tc):
                        if (sensor.adc.i2c == ADC.busnum) \
                         and (sensor.adc.addrs[sensor.adcIndex] == ADC.address) \
                         and (sensor.mux == mux):
                            if (sensor.name == "TC15@U15") or (sensor.name == "TC16@U15"):
                                result = (360*(Volts-0.5))+32 #for deg. F, 0.5V bias
                                #print sensor.name, "reads ", result, "F. 0.5V BIASED"
                                #print "I2C Address: ",sensor.adc.addrs[sensor.adcIndex],"AIN:",sensor.mux
                            else:
                                result = (360*Volts)+32 #for deg. F, 0V bias
                                #print sensor.name, "reads ", result, "F"
                                #print("I2C Address: 0x{:02x}, AIN: {},I2Cindex: {}" \
                                #  .format(sensor.adc.addrs[sensor.adcIndex],sensor.mux, sensor.adc.i2cIndex))
                            #result = random.random() * 200.0 ## DBG
                            sensor.appendAdcValue(result)
    pass

def fetchAdcInputs():    #NOTE will execute, but test sufficiently to verify reliable Data
    for mux in range(Lib.Adc.NMUX):
        for job in range(3): ## [ start, sleep, fetch ]
            for sensor in Lib.ains:
                if sensor.use and sensor.mux == mux: # and sensor.name == "TC5@U13":
                    adc = sensor.adc
                    if (job == 0): ## start
                        try:
                            adc.startAdc(mux, pga=4096, sps=250)  ## DWC 12.14 revert back to default sps=250, pga=4096
                            #print("job={} mux={} sensor={}"\     ## DWC 12.16 drop for now
                            #    .format(job,mux,sensor.name))
                        except Exception as err:
                            print("error starting ADC for sensor {} on Adc at 0x{:02x} mux {}: {}"\
                                    .format(sensor.name, adc.addr, mux, err))
                            adc.startTime = time.time() ## really needed?
                    elif (job == 1): ## sleep
                        elapsed = time.time() - adc.startTime 
                        adctime = (1.0 / adc.sps) + .001 
                        if (elapsed < adctime):
                            #print("fetching 0x{:02x} too early: at {} sps delay should be {} but is {}"\
                            #        .format(adc.addr, sensor.sps, adctime, elapsed))
                            time.sleep(adctime - elapsed + .002)
                        ## DWC 12.14 add print statement, take out of if statement
                        #print("job={} mux={} sensor={} adctime={} elapsed={}"\    ## DWC 12.16 drop for now
                        #    .format(job,mux,sensor.name,adctime,elapsed))
                    else: #if (job == 2): ## fetch
                        try:
                            Value = adc.fetchAdc()
                            if sensor.name[0:2] == "TC":  #perhaps break the conversion out from the read cycle?
                                sensor.appendAdcValue(Value) # conversions for Tcs are performed in AdcValue.
                                result = sensor.getLastVal()
                            else:
                                #print("this is not a TC."),  #DBG
                                result = Value #TODO other conversions?
                                #print("{} \tResult: {}mV"\
                                #    .format(sensor.name,result))
                                sensor.appendAdcValue(result)   ## TODO caution - should append only if accumulating longer record
                            print("{:6.2f} " .format(result), end='')    ## DWC 12.16 put output on one line for readability
                        except Exception as err:
                            print("error fetching ADC for sensor {} on Adc at 0x{:02x} mux {}: {}"\
                                    .format(sensor.name, adc.addr, mux, err))
    #print('\n')    ## DWC 121.26 comment out to create a single output line for inspection of data

    ## print in initial order
    ## DWC 12.14 comment out while using job-specific print statements above
    """
    for sensor in Lib.ains:
        print("sensor: {}  sps: {}  pga: {}  result: {}".format(sensor.name, adc.sps, adc.pga, sensor.getLastVal()))
    pass
    """
# DC 11.28 also need to do:  
# When done with DLVR reads, calculate average and range within the values
# Pressure sensor reads might be interleaved with i2c adc reads above, or
#  might be a separate function.

def fetchPressure():
    ## Read Pressure sensor check
    pressureAvg = 0.0
    count = 0
    for i in range(25):
        previous = time.time()
        try: 
            pressure_inH20 = Lib.p_zero.readPressure()
        except: 
            pressure_inH20 = NaN
            print("Pressure Reading Exception caught")
        if math.isnan(pressure_inH20):
            count -=1
        else:
          #print "Pressure is: {}".format(pressure_inH20),
          #print "time delay is: {}".format(time.time()-previous)
          pressureAvg = pressureAvg + pressure_inH20
        count += 1
        time.sleep(0.0066-(time.time()-previous)) 
                                  ## pressure is updated every 9.5mSec for low power
                                  ## The delay between adc updates is 6 m sec 
                                  ## for 31 cycles then it does an internal 
                                  ## check that takes 9.5. We should go just over 6 for our delay 
                                  ## and may get a duplicate reading occasionally. 
                                  ##

    if count != 0.0:
        pressureAvg = pressureAvg/count
    ## TEST PRINT
    if False:   
        print("count is: {} ".format(count), end='')
        print("pressureAvg is: {}".format(pressureAvg))
    return pressureAvg
    pass

# DC 11.28 New functions for building and writing records

def accumulateValues():       # DC 11.28 
    for sensor in Lib.sensors:
        sensor.value.sum(sensor.currentvalue)  # Add current val to running sum
        sensor.value.min(sensor.currentvalue)  # Compare current val to running min
        sensor.value.max(sensor.currentvalue)  # Compare curr ent val to running max
        sensor.value.count(sensor.currentvalue) # Track number of values for avg calc 
        # OR, accumulate values over the ~60 sec period, 
        #  and do the arithmetic at end of period:
        sensor.appendAdcValue(sensor.currentvalue) 

def closeOutRecord():      # DC 11.28 
    for sensor in Lib.sensors:
        # sensor.avg() = sensor.value.sum / sensor.value.count
        # Min & max values are up to date per accumulateValues() above
        sensor.avg()
    # Number of samples = sensorX.count where sensorX is e.g. TC1
    # Increment record number integer
    # Write base of record string (timestamp, systemID, record #, mon.state, wh.mode, f.mode)
    # Place data values in record string (see xlsx file for list of parameters)
    # Build string for output to file, using sensor.avg, sensor.min, 
    #  sensor.max values 
    # Write string to file - probably want a file write function in library?
    # Must clear all accumulated values when a record is closed out: 
    for sensor in Lib.sensors:
        sensor.value.clear()                 
    
def write1secRecord():      # DC 11.28 
    # wHen writing 1-second records, we simply write sensor.currentvalue 
    #  to the data record 
    # Number of samples = 1
    # Increment record number integer
    # Write base of record string (timestamp, systemID, record #, mon.state, wh.mode, f.mode)
    # Place data values in record string (see xlsx file for list of parameters)
    # Min and max values will simply be set to the single parameter value
    # Append record string to file
    # Clear accumulator objects (may not be necessary)
    pass



class Mon(object):
    """the combustion monitor"""
    State1Start = 1
    State2On = 2
    State3Stop = 3
    State4CoolDown = 4
    State5OffCO2 = 5
    State6Off = 6

    def __init__(self):
        self.__prevState = None
        #self.__state = None #= Mon.State6Off ## TODO?  commented 12.16
        self.__state = Mon.State6Off ## DWC 12.16 try this

    def getprevState(self): return self.__prevState
    #def setprevState(self, value): self.__prevState = value
    def setprevState(self): self.__prevState = self.__state ## DWC 12.16 drop passed "value", always set to current state
    def delprevState(self): del self.__prevState
    prevState = property(getprevState, setprevState, delprevState, "'prevState' property")

    def getstate(self): return self.__state
    def setstate(self, value): 
        self.__state = value
        pass
    def delstate(self): del self.__state
    state = property(getstate, setstate, delstate, "'state' property")


#############
## start main
#############
## setup Xbee (must be after def of fetchXbee)
xbee = zigbee.ZigBee(ser,callback=fetchXbee)  # for uart4 xbee coordinator
try:
    xBeeNodes = [ Conf.xBeeNode1, Conf.xBeeNode2, Conf.xBeeNode3 ] # create a list from value set
    xBeeNodeTypes = [ Conf.xBeeNode1Type, Conf.xBeeNode2Type, Conf.xBeeNode3Type ] 
    # TODO further error checking of these inputs
except:
    print("Error Parsing Xbee Addresses and Types from the Configuration File. Exiting")
    sys.exit()
    
for x in range(len(xBeeNodes)):  # for each xbee end node in the network
    nodeAddress = xBeeNodes[x]
    xbeeTemp = Lib.Xbee(name=("xbee-"+str(x)),adcIndex=0,address=nodeAddress,use=True)   #adc-1
    Lib.sensors.extend([xbeeTemp])
    xbeeTemp = Lib.Xbee(name=("xbee-"+str(x)),adcIndex=1,address=nodeAddress,use=True)   #adc-2
    Lib.sensors.extend([xbeeTemp])
    # now instantiate all the xbee Params list for record keeping.  This could be made prettier...
    if (x == 0):
        n_xbee1 = Lib.Param(["n_xbee1"],["integer"],[0]) # number of values accumulated from xbee1 since last record (for averaging values)
        if (xBeeNodeTypes[0] == "none"):
            vi_xbee1 = Lib.Param(["vi_xbee1"], ["NA"],[NaN])       # empty set
            vp_xbee1 = Lib.Param(["vp_xbee1"], ["NA"],[NaN])       # empty set
            vpos_xbee1 = Lib.Param(["vpos_xbee1"],["NA"],[NaN])    # empty set
            vbatt_xbee1 = Lib.Param(["vbatt_xbee1"],["NA"],[NaN])  # empty
        elif (xBeeNodeTypes[0] == "CT"):
            vi_xbee1 = Lib.AinParam("vi_xbee1", Lib.sensors[-2]) # voltage value of a current reading (should be "NaN" if not measuring current)
            vp_xbee1 = Lib.Param(["vp_xbee1"], ["NA"],[NaN])       # empty set
            vpos_xbee1 = Lib.Param(["vpos_xbee1"],["NA"],[NaN])    # empty set
        elif (xBeeNodeTypes[0] == "Pressure"):
            vi_xbee1 = Lib.Param(["vi_xbee1"], ["NA"],[NaN]) # empty set
            vp_xbee1 = Lib.AinParam("vp_xbee1", Lib.sensors[-2]) # voltage value of a pressure reading ("NaN" if not measuring pressure)
            vpos_xbee1 = Lib.Param(["vpos_xbee1"],["NA"],[NaN]) #empty set
        elif (xBeeNodeTypes[0] == "Door"):
            vi_xbee1 = Lib.Param(["vi_xbee1"], ["NA"],[NaN]) # empty set
            vp_xbee1 = Lib.Param(["vp_xbee1"], ["NA"],[NaN]) # empty set
            vpos_xbee1 = Lib.AinParam("vpos_xbee1",Lib.sensors[-2]) # voltage value of door position, if any ("NaN" if not)
        if (xBeeNodeTypes[0] != "none"):
            #always add vbatt, if xbee exists
            vbatt_xbee1 = Lib.AinParam("vbatt_xbee1",Lib.sensors[-1]) # battery voltage (should always read, NaN if zero values accumulated)
        Lib.params.extend([n_xbee1, vi_xbee1, vp_xbee1, vpos_xbee1, vbatt_xbee1])
        print("Xbee {} Address is {}".format(x,nodeAddress))
    if (x == 1):
        n_xbee2 = Lib.Param(["n_xbee2"],["integer"],[0]) # number of values accumulated from xbee1 since last record (for averaging values)
        if (xBeeNodeTypes[1] == "none"):
            vi_xbee2 = Lib.Param(["vi_xbee2"], ["NA"],[NaN])       # empty set
            vp_xbee2 = Lib.Param(["vp_xbee2"], ["NA"],[NaN])       # empty set
            vpos_xbee2 = Lib.Param(["vpos_xbee2"],["NA"],[NaN])    # empty set
            vbatt_xbee2 = Lib.Param(["vbatt_xbee2"],["NA"],[NaN])  # empty
        elif (xBeeNodeTypes[1] == "CT"):
            vi_xbee2 = Lib.AinParam("vi_xbee2", Lib.sensors[-2]) # voltage value of a current reading (should be "NaN" if not measuring current)
            vp_xbee2 = Lib.Param(["vp_xbee2"], ["NA"],[NaN])       # empty set
            vpos_xbee2 = Lib.Param(["vpos_xbee2"],["NA"],[NaN])    # empty set
        elif (xBeeNodeTypes[1] == "Pressure"):
            vi_xbee2 = Lib.Param(["vi_xbee2"], ["NA"],[NaN]) # empty set
            vp_xbee2 = Lib.AinParam("vp_xbee2", Lib.sensors[-2]) # voltage value of a pressure reading ("NaN" if not measuring pressure)
            vpos_xbee2 = Lib.Param(["vpos_xbee2"],["NA"],[NaN]) #empty set
        elif (xBeeNodeTypes[1] == "Door"):
            vi_xbee2 = Lib.Param(["vi_xbee2"], ["NA"],[NaN]) # empty set
            vp_xbee2 = Lib.Param(["vp_xbee2"], ["NA"],[NaN]) # empty set
            vpos_xbee2 = Lib.AinParam("vpos_xbee2",Lib.sensors[-2]) # voltage value of door position, if any ("NaN" if not)
        if (xBeeNodeTypes[1] != "none"):
            #always add vbatt, if xbee exists
            vbatt_xbee2 = Lib.AinParam("vbatt_xbee2",Lib.sensors[-1]) # battery voltage (should always read, NaN if zero values accumulated)
        Lib.params.extend([n_xbee2, vi_xbee2, vp_xbee2, vpos_xbee2, vbatt_xbee2])
        print("Xbee {} Address is {}".format(x,nodeAddress))
    if (x == 2):
        n_xbee3 = Lib.Param(["n_xbee3"],["integer"],[0]) # number of values accumulated from xbee1 since last record (for averaging values)
        if (xBeeNodeTypes[2] == "none"):
            vi_xbee3 = Lib.Param(["vi_xbee3"], ["NA"],[NaN])       # empty set
            vp_xbee3 = Lib.Param(["vp_xbee3"], ["NA"],[NaN])       # empty set
            vpos_xbee3 = Lib.Param(["vpos_xbee3"],["NA"],[NaN])    # empty set
            vbatt_xbee3 = Lib.Param(["vbatt_xbee3"],["NA"],[NaN])  # empty
        elif (xBeeNodeTypes[2] == "CT"):
            vi_xbee3 = Lib.AinParam("vi_xbee3", Lib.sensors[-2]) # voltage value of a current reading (should be "NaN" if not measuring current)
            vp_xbee3 = Lib.Param(["vp_xbee3"], ["NA"],[NaN])       # empty set
            vpos_xbee3 = Lib.Param(["vpos_xbee3"],["NA"],[NaN])    # empty set
        elif (xBeeNodeTypes[2] == "Pressure"):
            vi_xbee3 = Lib.Param(["vi_xbee3"], ["NA"],[NaN]) # empty set
            vp_xbee3 = Lib.AinParam("vp_xbee3", Lib.sensors[-2]) # voltage value of a pressure reading ("NaN" if not measuring pressure)
            vpos_xbee3 = Lib.Param(["vpos_xbee3"],["NA"],[NaN]) #empty set
        elif (xBeeNodeTypes[2] == "Door"):
            vi_xbee3 = Lib.Param(["vi_xbee3"], ["NA"],[NaN]) # empty set
            vp_xbee3 = Lib.Param(["vp_xbee3"], ["NA"],[NaN]) # empty set
            vpos_xbee3 = Lib.AinParam("vpos_xbee3",Lib.sensors[-2]) # voltage value of door position, if any ("NaN" if not)
        if (xBeeNodeTypes[2] != "none"):
            #always add vbatt, if xbee exists
            vbatt_xbee3 = Lib.AinParam("vbatt_xbee3",Lib.sensors[-1]) # battery voltage (should always read, NaN if zero values accumulated)
        Lib.params.extend([n_xbee3, vi_xbee3, vp_xbee3, vpos_xbee3, vbatt_xbee3])
        print("Xbee {} Address is {}".format(x,nodeAddress))

Lib.Adc.debug = False
AdaAdcU11 = ADS1x15(ic=ADS1115,address=0x48,busnum=2)
AdaAdcU13 = ADS1x15(ic=ADS1115,address=0x49,busnum=2) 
AdaAdcU14 = ADS1x15(ic=ADS1115,address=0x4a,busnum=2) 
AdaAdcU15 = ADS1x15(ic=ADS1115,address=0x4b,busnum=2) 
AdaAdcU8 = ADS1x15(ic=ADS1115,address=0x48,busnum=1) #CO Amp on Ain2
AdaAdcU9 = ADS1x15(ic=ADS1115,address=0x49,busnum=1) #CO2 on Ain0
AdaAdcU10 = ADS1x15(ic=ADS1115,address=0x4a,busnum=1)

wh = Lib.waterHtr
f = Lib.furnace

mon = Mon()

#Generate a Filename and Path (for Records)
dataFilename = Conf.savePath+time.strftime("%Y-%m-%d_%H_%M_%S_",time.gmtime())+Conf.siteName+"_Data.csv"
#Generate a Filename and Path (for Info/Diagnostics)
diagnosticsFilename = Conf.savePath+time.strftime("%Y-%m-%d_%H_%M_%S_",time.gmtime())+Conf.siteName+"_Info.csv"

#Record headers to Data File (for Records)
dataFile = open(dataFilename,'ab')
dataFile.write(Lib.record(HEADER_REC))
dataFile.close()
#TODO Record Units?

#Record diagnostics information


## determine the current state
## DWC 12.14 I don't think we want to fetch here, rather just start scans, and 
##  status/mode/state should sort themselves out in time.  Commented out.
#fetchAdcInputs()
#fetchTempsAdafruit([AdaAdcU11,AdaAdcU13,AdaAdcU14,AdaAdcU15]) #grab all ADC inputs from TC ADCs 

#################################################################################
## Initialization of values

pressstarttime = None
co2starttime   = None    ## DWC messy, used to avoid error on first scan
valveindexco2  = None
valveco2       = 0
co2_elapsed    = None
press_elapsed  = None
cnt = 0

## main loop
Lib.Timer.start()
Lib.Timer.sleep()
while True:
  try:  #NOTE this is for debug, except Keyboard Interrupt 
    ## Capture time at top of second
    ## DWC changed "tick" to "scantime".  This does appear to be real time (sample value 1418757518.0 sec ~< 45 yrs)
    scantime = Lib.Timer.stime()      
    #print("time at top of loop: {}".format(scantime))
    ## TEST PRINT
    if True: 
        print("{:>6.0f}" .format(scantime % 86400.0), end='')    ## % 86400 converts to seconds into GMT day, for testing only

    ## Scan all inputs
    fetchAdcInputs() 
    ## DWC drop fetchTempsAdafruit()
    #fetchTempsAdafruit([AdaAdcU11,AdaAdcU13,AdaAdcU14,AdaAdcU15])
    ## DWC 12.14 trial of fetch pressure() in line
    currentpressure = fetchPressure()
    ## TEST PRINT
    if True:
        print("{:>9.5f}".format(currentpressure), end='')    ## Not sure how extra newline in output is generated

    #print("Pressure now: {}".format(currentpressure))    ## DWC 12.16 drop for now, is printed within pressure routine
    
    #This following for loop for DBG  
    for mux in range(Lib.Adc.NMUX):
        for sensor in Lib.sensors:
         ## DWC 12.14 code hangs up here (Tc object has no attribute 'getLastVal')
        ##  so commented out
            """
            if isinstance(sensor, Lib.Tc) and sensor.mux == mux:
                if (sensor.getLastVal()-sensor.getPrevVal())>4:
                    print "Temp difference for {} is {}F".format(sensor.name,(sensor.getLastVal()-\
                      sensor.getPrevVal()))
            """
    #Read Pressure sensor check
    ## DWC 12.14 comment out, put in line above
            """
            if isinstance(sensor, Lib.Dlvr):
                sensor.setValves()
                sensor.appendValue(fetchPressure()) #TODO - do this right away or in Pressure Control?
            #   print "Pressure is: {}".format(sensor.getLastVal()) 
            """
        #if isinstance(sensor, Lib.Xbee):
        #    print "Xbee {} values: {}, {}".format(sensor.name,sensor.adc,sensor.getLastVal())
                
    #for burner in Lib.burners:
    #    burner.tc.appendAdcValue(random.random() * 200.0) ## added for DBG

    ## Process data
    ## Determine status of both burners
    ## Assign operating mode of wh and furnace
    whmode = wh.calcMode() ## also updates status (if burner is present) ## TODO
    fmode = f.calcMode() ## also updates status (if burner is present) ## TODO
    ## TEST PRINT
    if False:      ## DWC 12.14 activated to test (was if False:)
        print("furn temp: {:>5.1f}  fstatus:  {}  fmode: {} fprevMode: {} "\
                .format(f.tc.getLastVal(), f.getStatus(), fmode, f.prevMode))
        ## DWC 121.14 added similar print for wh:
        print("wh temp:   {:>5.1f}  whstatus: {}  whmode: {} whprevMode: {} "\
                .format(wh.tc.getLastVal(), wh.getStatus(), whmode, wh.prevMode))

    # DC we need to capture previous state before entering the state-setting routine
    #mon.setprevState(mon.getstate())   # DC 11.28 is this correct?

    ## Assign monitoring system state [these need to be re-checked thoroughly--TimC]
    mon.setprevState()     ## DWC 12.16
    if ((whmode == Lib.Burner.Mode2On) or (fmode == Lib.Burner.Mode2On)): ## at least one burner is on
        mon.state = Mon.State2On
    elif ((whmode == Lib.Burner.Mode1JustStarted) or (fmode == Lib.Burner.Mode1JustStarted)): ## first burner just started
        mon.state = Mon.State1Start
    elif ((whmode == Lib.Burner.Mode3JustStopped) or (fmode == Lib.Burner.Mode3JustStopped)): ## last burner just stopped
        mon.state = Mon.State3Stop
    elif ((whmode == Lib.Burner.Mode4Cooling) or (fmode == Lib.Burner.Mode4Cooling)): ## hold in state 4 even if burners have moved to state 5
        if True: ## DBG
            ## only switch state at top of minute  ## check for overrun
            lastStopTime = f.stopTime if (wh.stopTime < f.stopTime) else wh.stopTime
            if ((((scantime - lastStopTime) >= 120.0) and (datetime.utcfromtimestamp(scantime).second == 0)) or ((scantime - lastStopTime) >= 180.0)): 
                print("mon.state should be Mon.State6Off")
        mon.state = Mon.State4CoolDown
    elif ((whmode == Lib.Burner.Mode5Off) or (fmode == Lib.Burner.Mode5Off)): 
        mon.state = Mon.State6Off
    ## else no change

    ## Cycle between states 5 and 6 when both burners are off
    if (mon.state == Mon.State6Off):
        if ((math.trunc(scantime) % 900) < 60): ## in first minute of 15 minute interval
            ## TODO set flag to start CO2 measurement?
            mon.state = Mon.State5OffCO2
        ## else no change
    elif (mon.state == Mon.State5OffCO2):
        if ((math.trunc(scantime) % 900) >= 60): ## beyond first minute of 15 minute interval 
            mon.state = Mon.State6Off
        ## else no change
    ## else no change
    ## DWC 12.16 moved print statement to after state is set
    ## TEST PRINT
    if False:     
        print("time {:>12.1f} mon state: {}  prevState: {}  sw1: {}"\
            .format(scantime, mon.state, mon.prevState, Lib.sw1.getValue()))

    #for sensor in Lib.sensors:
	#	print sensor.name
    		       
    ## Pressure control routine

    ## TODO set up initialization of valve list to reflect presence of wh and/or furn
    valvelistpress = [0,1,2,3]       ## Pressure controls are 0, 1, 2, 3
    if (pressstarttime == None):    ## Initialize pressure start on first scan
        valvepress = 0
        valveindexpress = 0
        pressstarttime = scantime
    press_elapsed = scantime - pressstarttime
    if (((press_elapsed) >= PRESSVALVECYCLE) or ((press_elapsed) < 0)):
        try:
            valveindexpress = valvelistpress.index(valvepress)
            valveindexpress += 1
            if valveindexpress == (len(valvelistpress)):
                valveindexpress = 0
            valvepress = valvelistpress[valveindexpress]  
            pressstarttime = scantime
        except:
                print("could not execute CO2 valve indexing routine")
    
    if (mon.getstate() in [4,6]):     ## No CO2 monitoring
        valveco2 = 0           

    ## Set valves
    if (valvepress == 0):
        Lib.p_zero_valve.setValue(1)
        Lib.p_whvent_valve.setValue(0)
        Lib.p_fvent_valve.setValue(0)
        Lib.p_zone_valve.setValue(0)     
    elif (valvepress == 1):
        Lib.p_zero_valve.setValue(0)
        Lib.p_whvent_valve.setValue(1)
        Lib.p_fvent_valve.setValue(0)
        Lib.p_zone_valve.setValue(0)     
    elif (valvepress == 2):
        Lib.p_zero_valve.setValue(0)
        Lib.p_whvent_valve.setValue(0)
        Lib.p_fvent_valve.setValue(1)
        Lib.p_zone_valve.setValue(0)     
    elif (valvepress == 3):
        Lib.p_zero_valve.setValue(0)
        Lib.p_whvent_valve.setValue(0)
        Lib.p_fvent_valve.setValue(0)
        Lib.p_zone_valve.setValue(1)     
    else:
        print("No pressure valve set")
   
    
    
    
    ## CO2 control routine

    ## For use below: waterHeaterIsPresent furnaceIsPresent    

    ## CO2 valve control 
    ## initial valve setting    
    if (mon.getprevState() in [4,6]):    ## States w/ no CO2 monitoring
        if (mon.getstate() == 1):        ## First burner just started, set up valves
            if(whmode == 1):             ## Check which appliance started, go there first.  Won't see an absent appliance.
                valveco2 = 4             ## TODO Verify valve numbers.
            else: 
                valveco2 = 5        
            co2starttime = scantime
        elif (mon.getstate() == 5):      ## Starting 1-min CO2 sampling during Off period
            if(Conf.waterHeaterIsPresent):    ## Priority to water heater ifpresent
                valveco2 = 4    ## Verify valve numbers
            else: 
                valveco2 = 5  #start 
            co2starttime = scantime
     
    ## Valve cycling 
    ## TODO set up initialization of valve list to reflect presence of wh and/or furn
    ## TODO check for negative numbers in all time difference tests (in case of massive clock error)
    ## DWC initialized co2starttime to None to avoid a fault on startup
    valvelistco2 = [4,5,6]       ## Controls are numbered from 0; 4, 5, 6 are CO2 valves
    if (co2starttime != None):
        co2_elapsed = scantime - co2starttime
        if (((co2_elapsed) >= CO2VALVECYCLE) or ((co2_elapsed) < 0)):
            try:
                valveindexco2 = valvelistco2.index(valveco2)
                valveindexco2 += 1
                if valveindexco2 == (len(valvelistco2)):
                    valveindexco2 = 0
                valveco2 = valvelistco2[valveindexco2]  
                co2starttime = scantime
                print("CO2 valve indexing. Elapsed = {}"\
                .format (scantime-co2starttime))
            except:
                print("could not execute press valve indexing routine")
        
    if (mon.getstate() in [4,6]):     ## No CO2 monitoring
        valveco2 = 0           
    ## Set valves
    if (valveco2 == 4):
        Lib.co2_whvent_valve.setValue(1)
        Lib.co2_fvent_valve.setValue(0)
        Lib.co2_zone_valve.setValue(0)
        Lib.controls[7].setValue(1)     ## Pump
    elif (valveco2 == 5):
        Lib.co2_whvent_valve.setValue(0)
        Lib.co2_fvent_valve.setValue(1)
        Lib.co2_zone_valve.setValue(0)
        Lib.controls[7].setValue(1)     ## Pump
    elif (valveco2 == 6):
        Lib.co2_whvent_valve.setValue(0)
        Lib.co2_fvent_valve.setValue(0)
        Lib.co2_zone_valve.setValue(1)
        Lib.controls[7].setValue(1)     ## Pump
    else:
        Lib.co2_whvent_valve.setValue(0)
        Lib.co2_fvent_valve.setValue(0)
        Lib.co2_zone_valve.setValue(0)
        Lib.controls[7].setValue(0)     ## Pump

    ## TEST PRINT
    if False:     
        print ("valveindexpress = {} valvepress = {} press_elapsed = {} valveindexco2 = {} valveco2 = {} co2_elapsed = {}"\
            .format(valveindexpress, valvepress, press_elapsed, valveindexco2, valveco2, co2_elapsed))   
                   
    
    ## TODO Record control
    # DC 11.28 Start new code for Record Control
    # Is "scantime" the current time to 1 sec resolution?
    # Create "lastRecordTime" in seconds
    
    # Define 2 lists for state tests:
    prev_state_60sec   = [5,6]      # Monitoring states with 60-sec record interval
    current_state_1sec = [1,2,3,4]  # Monitoring states with 1-sec record interval
    
    ## Check triggers for closing out a 60-sec record  ##TODO
    #if ((mon.prevstate in prev_state_60sec) and ((math.trunc(scantime) % 60) == 0)): 
    #    closeOutRecord()    ## close out accumulated record
    ## Check for any record period reaching nominally 120 sec, regardless of state    
    #elif ((scantime - lastRecordTime) >= 120):
    #    closeOutRecord()     
    ## Finally, check for a state change into 1-sec data collection    
    #elif ((mon.prevstate in prev_state_60sec) and (mon.state in current_state_1sec)):
    #    closeOutRecord()     

        
    # Check current state; either write 1-sec record or accumulate values
    # Note we MAY close out a ~60-sec record AND write a 1-sec record during 
    #  a single scan.  :TODO
    #if (mon.state in current_state_1sec):
    #    write1secRecord()
    #else:
    #    accumulateValues()    # Accumulate values only when not currently in 1-sec
    
    # DC 11.28 End of new code


    ## Diagnostic record control
    ## Cleanup

    #Service watchdog
    try: 
        watchdog.write("\n")
        watchdog.flush() 
    except:
        print("unable to write to watchdog")
    
    # Check memory periodically? #TODO
    #freeDiskSpace = get_free_space_bytes(Conf.savePath)
    #if freeDiskSpace < 1000000:     
    #    print "Disk is full. Exiting"
    #    sys.exit()

    Lib.Timer.sleep()
    pass
    print()
    
  except KeyboardInterrupt: #DBG This is for debug (allows xbee halt and serial cleanup)
    break

## cleanup 
xbee.halt()
ser.close()
try: 
    dataFile.close()
except:
    print("Unable to close the DAT file currently being used")
