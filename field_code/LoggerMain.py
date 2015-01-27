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
##                 - dropped xbee print statement for testing
## 2015.01.22 DanC - Moved std out print statements to after all processing & edited header
##                 - Added status, mode and state info to std out
##                 - XBee values now just ADC count value
## 2015.01.24 DanC - Changed scantime to use integer seconds
## 2015.01.25 DanC - Pressure values in Pa, apply zero offset
## 2015.01.26 DanC - Assign pressure currentVal at time of measurement, but don't append until after record routine
## 2015.01.26 DanC - Incorporated Ben's XBee edits
 
from __future__ import print_function

import time, math, sys, os
from datetime import datetime
from decimal import *
import LoggerLib as Lib
import Adafruit_BBIO.UART as UART
from xbee import zigbee
import serial
import random

##########################################################################################
## Constants 
CO2VALVECYCLE = 20   ## CO2 valve operating cycle (sec)
CO2CLEARTIME  = 17   ## Time allowed for clearing CO2 system, good data comes after this
PRESSVALVECYCLE = 3
NaN = float('NaN')

#Record keeping
HEADER_REC = 0
UNITS_REC = 1
SINGLE_SCAN_REC = 2
MULTI_SCAN_REC = 3

# Path for remote rsync
rsyncPath = "/home/frsa/Data/2445_CS/"

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
    os.system("/srv/field-research/field-code/getUniqueID.sh") #run this to extract Serial Number for EEPROM
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


###########################################################################################
## local functions
# ==============================================================================

def get_free_space_bytes(folder):
    #command to check remaining free space on the storage device
    st = os.statvfs(folder)
    return st.f_bavail * st.f_frsize
    pass

def fetchXbee(data):
    global xbeeCaptureList #used for displaying captured values in stdout
    try:
        if False:       ## TEST PRINT
            print("Xbee data Received")
        for sensor in Lib.sensors:
            if isinstance(sensor, Lib.Xbee): #xbee-0,xbee-1,xbee-2
                matchAddress = False
                matchName = ""
                for item in data:
                    #print "item is",str(item)
                    if (str(item) == 'source_addr_long'):
                        #print '\t'+str(item),data[item].encode("hex")[12:16]
                        #print "addr_long is:",str(data[item].encode("hex")[12:16])
                        if ("0x"+str(data[item].encode("hex")[12:16])) == sensor.address:
                            matchAddress = True
                            matchName = sensor.name
                            #print "\tThere is a match",sensor.address
                    elif str(item) == 'samples':
                        samplesDict = data[item]
                        for x in samplesDict: #x will have several items, limit the selection
                            for y in x:  #There should only be 2 of interest in this list
                                if matchAddress and str(y) == str(sensor.adc):  #adc-1 or adc-2
                                    #print '\t'+str(y),x[y]*0.001173,"volts",sensor.adc 
                                    sensor.appendAdcValue(x[y]) # convert and record into volts for both ADC-1 and ADC-2
                                    if y == "adc-2": # increment correct n_xbee only once
                                        for param in Lib.params:
                                            fields = param.reportScanData()
                                            if (param.reportHeaders() == ['n_xbee1']) and sensor.name == "xbee-0":
                                                #print("\r\nn_xbee1 and xbee-0 Match")  ## DEBUG
                                                xbeeCaptureList[0] = sensor.getLastVal()
                                                #print("\r\n XB1:{:>4.2f} ".format(sensor.getLastVal()),end='') ## DEBUG
                                                #print("\r\nsetting Value: {}".format([fields[0]+1]))  ## DEBUG
                                                param.setValue(fields[0]+1)
                                            elif (param.reportHeaders() == ['n_xbee2']) and sensor.name == "xbee-1":
                                                #print("n_xbee2 and xbee-1 Match")
                                                xbeeCaptureList[1] = sensor.getLastVal()
                                                #print(" XB2:{:>4.2f} ".format(sensor.getLastVal()),end='')
                                                param.setValue(fields[0]+1)
                                            elif (param.reportHeaders() == ['n_xbee3']) and sensor.name == "xbee-2":
                                                #print("n_xbee3 and xbee-2 Match")
                                                xbeeCaptureList[2] = sensor.getLastVal()
                                                #print(" XB3:{:>4.2f} ".format(sensor.getLastVal()),end='')
                                                param.setValue(fields[0]+1)
                                    if y == "adc-1": # store VBATT into diagnostics Param
                                        for param in Lib.diagParams:
                                            if (param.reportHeaders() == ['vbatt_xbee1']) and sensor.name == "xbee-0":
                                                #print("\r\nvbatt_xbee1 and xbee-0 Match, vbatt1 storing:{}".format(sensor.getLastVal()))
                                                param.setValue(sensor.getLastVal())
                                                #print("\r\nValue of VBATT1 now:{}".format(param.values))  ## DEBUG
                                            elif (param.reportHeaders() == ['vbatt_xbee2']) and sensor.name == "xbee-1":
                                                #print("vbatt_xbee2 and xbee-1 Match, vbatt2 storing:{}".format(sensor.getLastVal()))
                                                param.setValue(sensor.getLastVal())
                                            elif (param.reportHeaders() == ['vbatt_xbee3']) and sensor.name == "xbee-2":
                                                #print("vbatt_xbee3 and xbee-2 Match, vbatt3 storing:{}".format(sensor.getLastVal()))
                                                param.setValue(sensor.getLastVal())

    except:
        print ("unable to print or parse xbee data")
    pass


def fetchAdcInputs():    #NOTE will execute, but test sufficiently to verify reliable Data
    global currentCO2value #used for handing off CO2 Value
    global adcCaptureList # contains list elements with [sensor.name, sensor.getLastVal()]
    for mux in range(Lib.Adc.NMUX):
        for job in range(3): ## [ start, sleep, fetch ]
            for sensor in Lib.ains:
                if sensor.use and sensor.mux == mux: # and sensor.name == "TC05@U13":
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
                            elif sensor.name == "J25-1@U9": #CO2 input
                                currentCO2value = Value #handoff to main loop
                                result = Value * 2 # conversion to CO2 ppm
                                #print("CurrentCO2value set to {}".format(currentCO2value))
                            else:
                                #print("this is not a TC."),  #DBG
                                #print("{} \tResult: {}mV"\
                                #    .format(sensor.name,result))
                                sensor.appendAdcValue(Value)
                                result = sensor.getLastVal()
                            adcCaptureList.append([sensor.name,result])
                            #print("{:4.0f} " .format(result), end='')    ## DWC 12.16 put output on one line for readability
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
        try: 
            pressure_Pa = Lib.p_current.readPressure()
        except: 
            pressure_Pa = NaN
            print("Pressure Reading Exception caught")
        if math.isnan(pressure_Pa):
            #print("Pressure is: {}".format(pressure_Pa))
            count -=1
        else:
          #print("Pressure is: {}".format(pressure_Pa))
          pressureAvg = pressureAvg + pressure_Pa
        count += 1
        time.sleep(0.0066) 
                                  ## pressure is updated every 9.5mSec for low power
                                  ## The delay between adc updates is 6 m sec 
                                  ## for 31 cycles then it does an internal 
                                  ## check that takes 9.5. We should go just over 6 for our delay 
                                  ## and may get a duplicate reading occasionally. 
                                  ##

    if count != 0.0:
        pressureAvg = pressureAvg/count
    if False:      ## TEST PRINT
        print("count is: {}".format(count), end='')
        print("pressureAvg is: {}".format(pressureAvg))
    return pressureAvg # returns oversampled pressure reading in inH20
    pass

# DC 11.28 New functions for building and writing records

#def accumulateValues():       # DC 11.28 
#    for sensor in Lib.sensors:
#        sensor.value.sum(sensor.currentvalue)  # Add current val to running sum
#        sensor.value.min(sensor.currentvalue)  # Compare current val to running min
#        sensor.value.max(sensor.currentvalue)  # Compare curr ent val to running max
#        sensor.value.count(sensor.currentvalue) # Track number of values for avg calc 
#        # OR, accumulate values over the ~60 sec period, 
#        #  and do the arithmetic at end of period:
#        #sensor.appendAdcValue(sensor.currentvalue) 
#    pass


def closeOutRecord():      # DC 11.28 
    # Number of samples = sensorX.count where sensorX is e.g. TC01
    number_of_samples = Lib.tcs[14].getValCntExceptLast() # this should be outdoor temp
    # Increment record number integer (This happens with Lib.record call.
    #print("TC14's Values are:{}".format(Lib.tcs[14].values)) ## DEBUG
    Lib.scans_accum.setValue(number_of_samples) #Set accumulator count
    #print("scans_accum is now: {}".format(Lib.scans_accum.values))  ## DEBUG
    Lib.sec_count.setValue(int(round(Decimal(scantime-lastRecordTime),0))) 
    #print("sec_count is now: {}".format(Lib.sec_count.values)) ## Debug
    # Write base of record string (timestamp, systemID, record #, mon.state, wh.mode, f.mode)
    # Place data values in record string (see xlsx file for list of parameters)
    # Build string for output to file, using sensor.avg, sensor.min, sensor.max values 
    # Write string to file - probably want a file write function in library?
    # Must clear all accumulated values when a record is closed out: 
    dataFile = open(dataFilename,'ab')
    dataFile.write(Lib.record(MULTI_SCAN_REC)+'\n')
    dataFile.close()
    ## Clear accumulator objects (may not be necessary)
    #print("Lib.sensors:{}".format(Lib.sensors))
    for sensor in Lib.sensors:
        #print("Sensor: {}; values: {}".format(sensor.name,sensor.values))
        if isinstance(sensor, Lib.Xbee): 
           if sensor.adc != "adc-1":  #single out VBAT as do-not-delete
               sensor.clearValues()
           #else:
               #print("Did not clear values for {} {}".format(sensor.name,sensor.adc))
        else:
            sensor.clearValuesExceptLast()
        #print("Sensor Name: {}, Sensor Value(s): {}".format(sensor.name,sensor.values))
    ## clear any non-sensor Params that accumulate
    for param in Lib.params:
        if "scans_accum" in param.headers:
            param.setValue(0)
        if "sec_count" in param.headers:
            param.setValue(0)
        if "n_xbee1" in param.headers:
            param.setValue(0)
        if "n_xbee2" in param.headers:
            param.setValue(0)
        if "n_xbee3" in param.headers:
            param.setValue(0)
    pass
    
def write1secRecord():      # DC 11.28 
    # wHen writing 1-second records, we simply write sensor.currentvalue 
    #  to the data record 
    # Number of samples should be = 1
    ## assign scans_accum the length of t_outdoor values (should be = 1)
    Lib.scans_accum.setValue(Lib.tcs[14].getValCnt()) #Set accumulator count
    #print("scans_accum is now: {}".format(Lib.scans_accum.values))  ## DEBUG
    Lib.sec_count.setValue(1) #Set this as a one or as a calculation?
    # Write base of record string (timestamp, systemID, record #, mon.state, wh.mode, f.mode)
    # Place data values in record string (see xlsx file for list of parameters)
    # Min and max values will simply be set to the single parameter value
    # Append record string to file
    dataFile = open(dataFilename,'ab')
    dataFile.write(Lib.record(SINGLE_SCAN_REC)+'\n')
    dataFile.close()
    ## Clear accumulator objects (may not be necessary)
    #print("Lib.sensors:{}".format(Lib.sensors))
    for sensor in Lib.sensors:
        #print("Sensor: {}; values: {}".format(sensor.name,sensor.values))
        if isinstance(sensor, Lib.Xbee): 
           if sensor.adc != "adc-1":  #single out VBAT as do-not-delete
               sensor.clearValues()
           #else:
               #print("Did not clear values for {} {}".format(sensor.name,sensor.adc))
        else:
            sensor.clearValues()
    ## clear any non-sensor Params that accumulate
    for param in Lib.params:
        if "scans_accum" in param.headers:
            param.setValue(0)
        if "sec_count" in param.headers:
            param.setValue(0)
        if "n_xbee1" in param.headers:
            param.setValue(0)
        if "n_xbee2" in param.headers:
            param.setValue(0)
        if "n_xbee3" in param.headers:
            param.setValue(0)
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
        self.__state = Mon.State6Off ## DWC 12.16 try this

    def getprevState(self): return self.__prevState
    #def setprevState(self, value): self.__prevState = value
    def setprevState(self): self.__prevState = self.__state ## DWC 12.16 drop passed "value", always set to current state
    def delprevState(self): del self.__prevState
    prevState = property(getprevState, setprevState, delprevState, "'prevState' property")

    def getstate(self): return self.__state
    def setstate(self, value): 
        self.__state = value
    def delstate(self): del self.__state
    state = property(getstate, setstate, delstate, "'state' property")


#############
## start main
#############
## setup Xbee (must be after def of fetchXbee)
xbee = zigbee.ZigBee(ser,callback=fetchXbee)  # for uart4 xbee coordinator
try:
    xBeeNodes = [ Conf.xBeeNode1.lower(), Conf.xBeeNode2.lower(), Conf.xBeeNode3.lower() ] # create a list from value set
    xBeeNodeTypes = [ Conf.xBeeNode1Type.lower(), Conf.xBeeNode2Type.lower(), Conf.xBeeNode3Type.lower() ] 
    # TODO further error checking of these inputs
except:
    print("Error Parsing Xbee Addresses and Types from the Configuration File. Exiting")
    sys.exit()
    
for x in range(len(xBeeNodes)):  # for each xbee end node in the network
    nodeAddress = xBeeNodes[x]
    xbeeTemp = Lib.Xbee(name=("xbee-"+str(x)),adcIndex=0,address=nodeAddress,use=True)   #adc-1 is vbatt
    Lib.sensors.extend([xbeeTemp])
    xbeeTemp = Lib.Xbee(name=("xbee-"+str(x)),adcIndex=1,address=nodeAddress,use=True)   #adc-2 is analog in
    Lib.sensors.extend([xbeeTemp])
    # now instantiate all the xbee Params list for record keeping.  This could be made prettier...
    if (x == 0):
        n_xbee1 = Lib.Param(["n_xbee1"],["integer"],[0]) # number of values accumulated from xbee1 since last record (for averaging values)
        if (xBeeNodeTypes[0] == "none"):
            vi_xbee1 = Lib.Param(["vi_xbee1"], ["NA"],[Decimal(NaN)])       # empty set
            vp_xbee1 = Lib.Param(["vp_xbee1"], ["NA"],[Decimal(NaN)])       # empty set
            vpos_xbee1 = Lib.Param(["vpos_xbee1"],["NA"],[Decimal(NaN)])    # empty set
            vbatt_xbee1 = Lib.Param(["vbatt_xbee1"],["NA"],[Decimal(NaN)])  # empty
        elif (xBeeNodeTypes[0] == "ct"):
            vi_xbee1 = Lib.XbeeParam("vi_xbee1", Lib.sensors[-1]) # voltage value of a current reading (should be "NaN" if not measuring current)
            vp_xbee1 = Lib.Param(["vp_xbee1"], ["NA"],[Decimal(NaN)])       # empty set
            vpos_xbee1 = Lib.Param(["vpos_xbee1"],["NA"],[Decimal(NaN)])    # empty set
            vbatt_xbee1 = Lib.XbeeParam("vbatt_xbee1",Lib.sensors[-2]) # battery voltage (should always read, NaN if zero values accumulated)
        elif (xBeeNodeTypes[0] == "pressure"):
            vi_xbee1 = Lib.Param(["vi_xbee1"], ["NA"],[Decimal(NaN)]) # empty set
            vp_xbee1 = Lib.XbeeParam("vp_xbee1", Lib.sensors[-1]) # voltage value of a pressure reading ("NaN" if not measuring pressure)
            vpos_xbee1 = Lib.Param(["vpos_xbee1"],["NA"],[Decimal(NaN)]) #empty set
            vbatt_xbee1 = Lib.XbeeParam("vbatt_xbee1",Lib.sensors[-2]) # battery voltage (should always read, NaN if zero values accumulated)
        elif (xBeeNodeTypes[0] == "door"):
            vi_xbee1 = Lib.Param(["vi_xbee1"], ["NA"],[Decimal(NaN)]) # empty set
            vp_xbee1 = Lib.Param(["vp_xbee1"], ["NA"],[Decimal(NaN)])       # empty set
            vpos_xbee1 = Lib.XbeeParam("vpos_xbee1",Lib.sensors[-1]) # voltage value of door position, if any ("NaN" if not)
            vbatt_xbee1 = Lib.XbeeParam("vbatt_xbee1",Lib.sensors[-2]) # battery voltage (should always read, NaN if zero values accumulated)
        Lib.params.extend([n_xbee1, vi_xbee1, vp_xbee1, vpos_xbee1])
        print("Xbee {} Address is {}".format(x,nodeAddress))
    if (x == 1):
        n_xbee2 = Lib.Param(["n_xbee2"],["integer"],[0]) # number of values accumulated from xbee1 since last record (for averaging values)
        if (xBeeNodeTypes[1] == "none"):
            vi_xbee2 = Lib.Param(["vi_xbee2"], ["NA"],[Decimal(NaN)])       # empty set
            vp_xbee2 = Lib.Param(["vp_xbee2"], ["NA"],[Decimal(NaN)])       # empty set
            vpos_xbee2 = Lib.Param(["vpos_xbee2"],["NA"],[Decimal(NaN)])    # empty set
            vbatt_xbee2 = Lib.Param(["vbatt_xbee2"],["NA"],[Decimal(NaN)])  # empty
        elif (xBeeNodeTypes[1] == "ct"):
            vi_xbee2 = Lib.XbeeParam("vi_xbee2", Lib.sensors[-1]) # voltage value of a current reading (should be "NaN" if not measuring current)
            vp_xbee2 = Lib.Param(["vp_xbee2"], ["NA"],[Decimal(NaN)])       # empty set
            vpos_xbee2 = Lib.Param(["vpos_xbee2"],["NA"],[Decimal(NaN)])    # empty set
            vbatt_xbee2 = Lib.XbeeParam("vbatt_xbee2",Lib.sensors[-2]) # battery voltage (should always read, NaN if zero values accumulated)
        elif (xBeeNodeTypes[1] == "pressure"):
            vi_xbee2 = Lib.Param(["vi_xbee2"], ["NA"],[Decimal(NaN)])       # empty set
            vp_xbee2 = Lib.XbeeParam("vp_xbee2", Lib.sensors[-1]) # voltage value of a pressure reading ("NaN" if not measuring pressure)
            vpos_xbee2 = Lib.Param(["vpos_xbee2"],["NA"],[Decimal(NaN)])    # empty set
            vbatt_xbee2 = Lib.XbeeParam("vbatt_xbee2",Lib.sensors[-2]) # battery voltage (should always read, NaN if zero values accumulated)
        elif (xBeeNodeTypes[1] == "door"):
            vi_xbee2 = Lib.Param(["vi_xbee2"], ["NA"],[Decimal(NaN)])       # empty set
            vp_xbee2 = Lib.Param(["vp_xbee2"], ["NA"],[Decimal(NaN)])       # empty set
            vpos_xbee2 = Lib.XbeeParam("vpos_xbee2",Lib.sensors[-1]) # voltage value of door position, if any ("NaN" if not)
            vbatt_xbee2 = Lib.XbeeParam("vbatt_xbee2",Lib.sensors[-2]) # battery voltage (should always read, NaN if zero values accumulated)
        Lib.params.extend([n_xbee2, vi_xbee2, vp_xbee2, vpos_xbee2])
        print("Xbee {} Address is {}".format(x,nodeAddress))
    if (x == 2):
        n_xbee3 = Lib.Param(["n_xbee3"],["integer"],[0]) # number of values accumulated from xbee1 since last record (for averaging values)
        if (xBeeNodeTypes[2] == "none"):
            vi_xbee3 = Lib.Param(["vi_xbee3"], ["NA"],[Decimal(NaN)])       # empty set
            vp_xbee3 = Lib.Param(["vp_xbee3"], ["NA"],[Decimal(NaN)])       # empty set
            vpos_xbee3 = Lib.Param(["vpos_xbee3"],["NA"],[Decimal(NaN)])    # empty set
            vbatt_xbee3 = Lib.Param(["vbatt_xbee3"],["NA"],[Decimal(NaN)])  # empty
        elif (xBeeNodeTypes[2] == "ct"):
            vi_xbee3 = Lib.AinParam("vi_xbee3", Lib.sensors[-1]) # voltage value of a current reading (should be "NaN" if not measuring current)
            vp_xbee3 = Lib.Param(["vp_xbee3"], ["NA"],[Decimal(NaN)])       # empty set
            vpos_xbee3 = Lib.Param(["vpos_xbee3"],["NA"],[Decimal(NaN)])    # empty set
            vbatt_xbee3 = Lib.AinParam("vbatt_xbee3",Lib.sensors[-2]) # battery voltage (should always read, NaN if zero values accumulated)
        elif (xBeeNodeTypes[2] == "pressure"):
            vi_xbee3 = Lib.Param(["vi_xbee3"], ["NA"],[Decimal(NaN)])       # empty set
            vp_xbee3 = Lib.AinParam("vp_xbee3", Lib.sensors[-1]) # voltage value of a pressure reading ("NaN" if not measuring pressure)
            vpos_xbee3 = Lib.Param(["vpos_xbee3"],["NA"],[Decimal(NaN)])    # empty set
            vbatt_xbee3 = Lib.AinParam("vbatt_xbee3",Lib.sensors[-2]) # battery voltage (should always read, NaN if zero values accumulated)
        elif (xBeeNodeTypes[2] == "door"):
            vi_xbee3 = Lib.Param(["vi_xbee3"], ["NA"],[Decimal(NaN)])       # empty set
            vp_xbee3 = Lib.Param(["vp_xbee3"], ["NA"],[Decimal(NaN)])       # empty set
            vpos_xbee3 = Lib.AinParam("vpos_xbee3",Lib.sensors[-1]) # voltage value of door position, if any ("NaN" if not)
            vbatt_xbee3 = Lib.AinParam("vbatt_xbee3",Lib.sensors[-2]) # battery voltage (should always read, NaN if zero values accumulated)
        Lib.params.extend([n_xbee3, vi_xbee3, vp_xbee3, vpos_xbee3])
        print("Xbee {} Address is {}".format(x,nodeAddress))

wh = Lib.waterHtr
f = Lib.furnace

mon = Mon()

## Check SiteName
BBBsiteName = Conf.siteName
## write handoff file that rsync file will use for rsync path and local path
siteRsyncPathFile = open("siteRsyncPath","w")
if BBBsiteName == "none": #if the sitename hasn't been changed from default...
    BBBsiteName = uniqueID
siteRsyncPathFile.write(rsyncPath+BBBsiteName)  ## handoff file for rsync (path of sync destination)
siteRsyncPathFile.close()

siteLocalDataFile = open("localDataPath","w") ## additional handoff to rsync
if Conf.savePath[-1:] == '/':
    siteLocalDataFile.write(Conf.savePath)
else:
    siteLocalDataFile.write(Conf.savePath+'/')
siteLocalDataFile.close()

## Handoff of site's reverse SSH port to shell scripts:
BBBreverseSSH = Conf.reverseSSHport
## check if it's changed from default.
if BBBreverseSSH == 7000: #if the port hasn't been changed from default...
    print("BBB reverse SSH port configuration has not been set.  Open LoogerConfig.py and set it.  Exiting...")
    sys.exit()
siteRSSHPortFile = open("reverseSSHport","w")
siteRSSHPortFile.write(str(BBBreverseSSH))  ## handoff port for scripts
siteRSSHPortFile.close()

## Generate a Filename and Path (for Records)
dataFilename = Conf.savePath+time.strftime("%Y-%m-%d_%H_%M_%S_",time.gmtime())+BBBsiteName+"_Data.csv"
## Generate a Filename and Path (for Info/Diagnostics)
diagnosticsFilename = Conf.savePath+time.strftime("%Y-%m-%d_%H_%M_%S_",time.gmtime())+BBBsiteName+"_Info.csv"

#Record headers to Data File (for Records)
dataFile = open(dataFilename,'ab')
dataFile.write(Lib.record(HEADER_REC)+"\n")
dataFile.close()
#TODO Record Units Somewhere.  Where?

## Record diagnostics information
diagnosticsFile= open(diagnosticsFilename,'ab')
BBB_id = Lib.Param(["BBB_ID"],[""],[uniqueID]) #Build any additional items TODO
BBB_xBeeNodes = Lib.Param(["xBeeNodes"],["Hex Addresses"],[str(xBeeNodes).replace(","," ")])
BBB_xBeeNodeTypes = Lib.Param(["xBeeNodeTypes"],["Sensor Type"],[str(xBeeNodeTypes).replace(","," ")])
BBB_CO_Calibration = Lib.Param(["CO_Calib_Factor"],["int"],[Conf.co_calib_value])
BBB_WH_is_present = Lib.Param(["WHisPresent"],["bool"],[Conf.waterHeaterIsPresent])
BBB_F_is_present = Lib.Param(["WHisPresent"],["bool"],[Conf.furnaceIsPresent])
BBB_reverseSSHport = Lib.Param(["reverseSSHport"],["int"],[Conf.reverseSSHport])
Lib.diagParams.extend([BBB_id, BBB_CO_Calibration, BBB_WH_is_present, \
        BBB_F_is_present, BBB_xBeeNodes, BBB_xBeeNodeTypes, BBB_reverseSSHport])
Lib.diagParams.extend([vbatt_xbee1,vbatt_xbee2,vbatt_xbee3])
BBB_rsync_save_path = Lib.Param(["rsync_savePath"],["string"],[rsyncPath+BBBsiteName])
Lib.diagParams.extend([BBB_rsync_save_path])
diagnosticsFile.write(Lib.diag_record(HEADER_REC)+"\n")
diagnosticsFile.write(Lib.diag_record(SINGLE_SCAN_REC)+"\n")
diagnosticsFile.close()
lastDiagTime = time.time() - ((time.time() % 86400.0)+1)  ## First instantiation of Diagnostic output and funny math to get next end of day recorded.

## determine the current state
## DWC 12.14 I don't think we want to fetch here, rather just start scans, and 
##  status/mode/state should sort themselves out in time.  Commented out.
#fetchAdcInputs()

#################################################################################
## Initialization of values

pressstarttime = None
valvepress = 0
press_elapsed  = None
valvepressname = "-"
co2starttime   = None    ## DWC messy, used to avoid error on first scan
currentCO2value = Decimal("NaN") ## used in handoff between function calls within PythonMain
valveindexco2  = None
valveco2       = 0
valveCO2name = "-"
co2_elapsed    = None
cnt = 0
lastRecordTime = time.time()
xbeeCaptureList = [NaN,NaN,NaN]
adcCaptureList = list()

#Print Header for stdout
headerString = "                  -- CO2 -- door Fan Fan CO-   ---- Water Heater ----  ------- Furnace ------   T Room Out     \
-- Press --  XB1  XB2  XB3 WH- Fur St elap\n\
       Time        Vlv  ppm  mV  -1- -2- ppm  Br  Sa  Sb  Sc  Sd  Vt  Br  Sa  Sb  Sc  Sd  Vt  Hi  Lo  To  -- \
Vlv   Pa   cnt  cnt  cnt smp smp SP elap"
print(headerString)

## main loop
Lib.Timer.start()
Lib.Timer.sleep()
while True:
  try:  #NOTE this is for debug, except Keyboard Interrupt 
    ## Capture time at top of second
    ## DWC 01.24 changed to time.time() because stime() doesn't update after sleep cycle ends
    ## scantimeusec now used for high-resolution timestamp, and scantime for 1-sec resolution
    scantimeusec = time.time()      
    Lib.timest.setValue(Lib.TIME(scantimeusec)) # track/record latest timestamp  (Is this used?)
    ## DWC create scantimesec (integer seconds) for valve control; fractional seconds throw it off
    scantime = math.trunc(scantimeusec)

    ## Scan all adc inputs
    fetchAdcInputs() 
    ## Sort these by name
    adcCaptureList.sort(key=lambda x: x[0])  # Sort list by first element, sensor.name
    ## the CO2 input is scanned 3 times and is in the front of the list, so drop two front values ("J25-1@U9")
    adcCaptureList.remove(adcCaptureList[0])
    adcCaptureList.remove(adcCaptureList[0])
    ## DWC 01.22 moved std out print statements to end of Main
                                    
    currentpressure = fetchPressure()
    currentpressurevalve = valvepress
    ## DWC 01.25 adjust for current zero offset, use try to avoid initialization problem
    if Lib.p_zero.currentVal == NaN:
        zeroOffset = 0
    else:
        zeroOffset = Lib.p_zero.currentVal 

    if False:
        print("Current pressure: {:7.3f} Zero offset: {:7.3f} Valve: {:02d}" .format(currentpressure, zeroOffset, currentpressurevalve))
    try:
        ## Update zero offset
        if currentpressurevalve == 0:
            Lib.p_zero.setCurrentVal(currentpressure)
        else:
            currentpressure = (currentpressure - zeroOffset)  ## Apply zero offset to stick through end of scan incl std out
        ## Update other values
        if currentpressurevalve == 1:
            Lib.p_whvent.setCurrentVal(currentpressure)
        elif currentpressurevalve == 2:
            Lib.p_fvent.setCurrentVal(currentpressure)
        elif currentpressurevalve == 3:
            Lib.p_zone.setCurrentVal(currentpressure)
    except:
        print("could not set current pressure value") 
    if False:
        print("{:7.3f} {:7.3f} {:7.3f} {:7.3f}" .format(Lib.p_zero.currentVal, Lib.p_whvent.currentVal,Lib.p_fvent.currentVal, Lib.p_zone.currentVal))
  
    if False: #DEBUG for burner sequencing
        for burner in Lib.burners: ## DEBUG
            burner.tc.appendAdcValue(random.random() * 200.0) ## added for DBG

    ## Process data
    ## Determine status of both burners
    ## Assign operating mode of wh and furnace
    whmode = wh.calcMode() ## also updates status (if burner is present) ## TODO
    Lib.whburner_stat.setValue(int(wh.getStatus())) ## update params to record
    Lib.whburner_mode.setValue(int(whmode))
    fmode = f.calcMode() ## also updates status (if burner is present) ## TODO
    Lib.fburner_stat.setValue(int(f.getStatus())) ## update params to record
    Lib.fburner_mode.setValue(int(fmode))
    # DEBUG
    #print("whmodeParam(Status,Mode) is:{},{}, fburnerParam(Status,Mode) is:{},{}".format( \
    #        Lib.whburner_stat.reportScanData(), Lib.whburner_mode.reportScanData(), \
    #        Lib.fburner_stat.reportScanData(),Lib.fburner_mode.reportScanData()))
    if False:          ## TEST PRINT
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
        if whmode == Lib.Burner.Mode2On:
            Lib.sec_whrun.setValue(Lib.sec_whrun.reportScanData()[0]+1)
        if fmode == Lib.Burner.Mode2On:
            Lib.sec_frun.setValue(Lib.sec_frun.reportScanData()[0]+1)
    elif ((whmode == Lib.Burner.Mode1JustStarted) or (fmode == Lib.Burner.Mode1JustStarted)): ## first burner just started
        mon.state = Mon.State1Start
        if whmode == Lib.Burner.Mode1JustStarted:
            Lib.sec_whrun.setValue(Lib.sec_whrun.reportScanData()[0]+1)
        if fmode == Lib.Burner.Mode1JustStarted:
            Lib.sec_frun.setValue(Lib.sec_frun.reportScanData()[0]+1)
    elif ((whmode == Lib.Burner.Mode3JustStopped) or (fmode == Lib.Burner.Mode3JustStopped)): ## last burner just stopped
        mon.state = Mon.State3Stop
    elif ((whmode == Lib.Burner.Mode4Cooling) or (fmode == Lib.Burner.Mode4Cooling)): ## hold in state 4 even if burners have moved to state 5
        if True: ## DBG
            ## only switch state at top of minute  ## check for overrun
            lastStopTime = f.stopTime if (wh.stopTime < f.stopTime) else wh.stopTime
            if ((((scantime - lastStopTime) >= 120.0) and (datetime.utcfromtimestamp(scantime).second == 0)) or ((scantime - lastStopTime) >= 180.0)): 
                print("mon.state should be Mon.State6Off")
        mon.state = Mon.State4CoolDown
        if whmode == Lib.Burner.Mode4Cooling:  ## count up the active time for cooling
            Lib.sec_whcooldown.setValue(Lib.sec_whcooldown.reportScanData()[0]+1)
        if fmode == Lib.Burner.Mode4Cooling:
            Lib.sec_fcooldown.setValue(Lib.sec_fcooldown.reportScanData()[0]+1)
    elif ((whmode == Lib.Burner.Mode5Off) or (fmode == Lib.Burner.Mode5Off)): 
        mon.state = Mon.State6Off
        if whmode == Lib.Burner.Mode5Off:  ## Clear accumulated values for all wh counts
            Lib.sec_whrun.setValue(0)
            Lib.sec_whcooldown.setValue(0)
        if fmode == Lib.Burner.Mode5Off:
            Lib.sec_frun.setValue(0)
            Lib.sec_fcooldown.setValue(0)

    ## else no change
    ## Cycle between states 5 and 6 when both burners are off
    if (mon.state == Mon.State6Off):
        if ((scantime % 900) < 60): ## in first minute of 15 minute interval
            ## TODO set flag to start CO2 measurement?
            mon.state = Mon.State5OffCO2
        ## else no change
    elif (mon.state == Mon.State5OffCO2):
        if ((scantime % 900) >= 60): ## beyond first minute of 15 minute interval 
            mon.state = Mon.State6Off
        ## else no change
    ## else no change
    ## record the params for states 
    Lib.monitor.setValue(int(mon.state))
    ## DWC 12.16 moved print statement to after state is set
    if False:         ## TEST PRINT
        print("time {:>12.1f} mon state: {}  prevState: {}  sw1: {}"\
            .format(scantime, mon.state, mon.prevState, Lib.sw1.getValue()))
    


    if False:
        for sensor in Lib.sensors:
            if isinstance(sensor, Lib.Xbee):
                print("{} ADC {}".format(sensor.name,sensor.adc))
            else:
                print("{}".format(sensor.name))
    		       
    ## Pressure control routine

    ## set up initialization of valve list to reflect presence of wh and/or furn
    valvelistpress = [0,1,2,3]       ## Pressure controls are 0, 1, 2, 3
    if Conf.waterHeaterIsPresent == False:
        valvelistpress.remove(1)  # Solenoid 1 serves WH sampling
    if Conf.furnaceIsPresent == False:
        valvelistpress.remove(2) # Solenoid 2 is the Furnace sampling
    
    if (pressstarttime == None):    ## Initialize pressure start on first scan
        valvepress = 0  # This duplicates command issued during initialization
        Lib.p_valve_pos.setValue(int(valvepress)) ## set initial value of Parameter "loc_p"
        valveindexpress = 0
        pressstarttime = scantime
    press_elapsed = scantime - pressstarttime
    if (((press_elapsed) >= PRESSVALVECYCLE) or ((press_elapsed) < 0)):
        ## DWC 01.25 reduce this to just switching valves
        valveindexpress = valvelistpress.index(valvepress)
        valveindexpress += 1
        if valveindexpress == (len(valvelistpress)):
            valveindexpress = 0
        valvepress = valvelistpress[valveindexpress]  
        pressstarttime = scantime

        """
        try:
            ## first store the fetched pressure for the previous valve setting
            if valvepress == 0:
                Lib.p_zero.appendAdcValue(currentpressure)
            elif valvepress == 1:
                Lib.p_whvent.appendAdcValue(currentpressure)
            elif valvepress == 2:
                Lib.p_fvent.appendAdcValue(currentpressure)
            elif valvepress == 3:
                Lib.p_zone.appendAdcValue(currentpressure)
            ## next, update valve index
            valveindexpress = valvelistpress.index(valvepress)
            valveindexpress += 1
            if valveindexpress == (len(valvelistpress)):
                valveindexpress = 0
            valvepress = valvelistpress[valveindexpress]  
            pressstarttime = scantime
            # Lib.p_valve_time.setValue(int(0)) ## reset time elapsed  ## DWC 01.25 dropping lines not used
            # Lib.p_valve_pos.setValue(int(valvepress)) ## update present valve setting
        except:
            print("could not execute pressure valve indexing routine")
        """    
    ## DWC 01.24 I don't think we use this:        
    #else: 
        #Lib.p_valve_time.setValue(int(round(Decimal(scantime-pressstarttime),0))) ## increment valve dwell counter
        
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
                valveco2 = 4             ## Verify valve numbers.
            else: 
                valveco2 = 5        
        elif (mon.getstate() == 5):      ## Starting 1-min CO2 sampling during Off period
            if(Conf.waterHeaterIsPresent):    ## Priority to water heater ifpresent
                valveco2 = 4    ## Verify valve numbers
            else: 
                valveco2 = 5  #start 
        co2starttime = scantime
        Lib.co2_valve_pos.setValue(int(valveco2)) ## set initial value of Parameter "loc_co2"
     
    ## Valve cycling 
    ## set up initialization of valve list to reflect presence of wh and/or furn
    valvelistco2 = [4,5,6]       ## Controls are numbered from 0; 4, 5, 6 are CO2 valves
    if Conf.waterHeaterIsPresent == False:
        valvelistco2.remove(4)  # Solenoid 1 serves WH sampling
    if Conf.furnaceIsPresent == False:
        valvelistco2.remove(5) # Solenoid 2 is the Furnace sampling
    
    ## TODO check for negative numbers in all time difference tests (in case of massive clock error)
    ## DWC initialized co2starttime to None to avoid a fault on startup
    if (co2starttime != None):
        co2_elapsed = scantime - co2starttime
        if (((co2_elapsed) >= CO2VALVECYCLE) or ((co2_elapsed) < 0)):
            try:
                ## first store the fetched pressure for the previous valve setting
                if valveco2 == 4:
                    #print("\nStoring {} into co2_whvent".format(currentCO2value))
                    Lib.co2_whvent.appendAdcValue(currentCO2value) # record sensor value
                elif valveco2 == 5:
                    #print("\nStoring {} into co2_fvent".format(currentCO2value))
                    Lib.co2_fvent.appendAdcValue(currentCO2value) # record sensor value
                elif valveco2 == 6:
                    #print("\nStoring {} into co2_zone".format(currentCO2value))
                    Lib.co2_zone.appendAdcValue(currentCO2value) # record sensor value
                ## next, update valve index
                valveindexco2 = valvelistco2.index(valveco2)
                valveindexco2 += 1
                if valveindexco2 == (len(valvelistco2)):
                    valveindexco2 = 0
                valveco2 = valvelistco2[valveindexco2]  
                co2starttime = scantime
                Lib.co2_valve_time.setValue(int(0)) ## reset time elapsed
                Lib.co2_valve_pos.setValue(int(valveco2)) ## update present valve setting
                print("CO2 valve indexing. Elapsed = {}"\
                .format (scantime-co2starttime))
            except:
                print("could not execute press valve indexing routine")
        else: ## wait for scan cycles before changing active valve  ## DWC 01.24 I don't think this is used or needed:
            Lib.co2_valve_time.setValue(int(round(Decimal(scantime-co2starttime),0))) ## increment valve dwell counter

    if (mon.getstate() in [4,6]):     ## No CO2 monitoring
        valveco2 = 0           


    ## Set co2 valves
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

    if False:         ## TEST PRINT
        print ("valveindexpress = {} valvepress = {} press_elapsed = {} valveindexco2 = {} valveco2 = {} co2_elapsed = {}"\
            .format(valveindexpress, valvepress, press_elapsed, valveindexco2, valveco2, co2_elapsed))   
 
    
    ## Record control    
    ## Diagnostic record control (Do this before values get cleared).  Recorded daily
    if ((((scantime - lastDiagTime) >= 86400.0) and (datetime.utcfromtimestamp(scantime).hour == 0)\
        and (datetime.utcfromtimestamp(scantime).minute == 0)) or ((scantime - lastDiagTime) >= 129600)): #Daily Diagnostic Record
    #if ((((scantime - lastDiagTime) >= 60.0) and (datetime.utcfromtimestamp(scantime).second == 0)) or ((scantime - lastDiagTime) >= 180.0)): ## DEBUG Interval
        #print("Writing Diagnostics File")
        diagnosticsFile= open(diagnosticsFilename,'ab')
        diagnosticsFile.write(Lib.diag_record(SINGLE_SCAN_REC)+"\n")
        diagnosticsFile.close()
        lastDiagTime = scantime
        #TODO: clear/zero any diagParams or sensor data?
        for sensor in Lib.sensors:
            #print("Sensor: {}; values: {}".format(sensor.name,sensor.values))
            if isinstance(sensor, Lib.Xbee): 
               if sensor.adc == "adc-2":  #single out VBAT as do-not-delete
                   sensor.clearValues()
                   #print("cleared VBATT values")
    

    # Define 2 lists for state tests:
    prev_state_60sec   = [5,6]      # Monitoring states with 60-sec record interval
    current_state_1sec = [1,2,3,4]  # Monitoring states with 1-sec record interval
    
    ## Check triggers for closing out a 60-sec record 
    if ((mon.getprevState() in prev_state_60sec) and ((scantime % 60) == 0)):  
        #print("Closing out Record")  ## DEBUG
        closeOutRecord()    ## close out accumulated record
        lastRecordTime = scantime
    ## Check for any record period reaching nominally 120 sec, regardless of state    
    elif ((scantime - lastRecordTime) >= 120):
        #print("Closing out Record")  ## DEBUG
        closeOutRecord()     
        lastRecordTime = scantime
    ## Finally, check for a state change into 1-sec data collection    
    elif ((mon.getprevState() in prev_state_60sec) and (mon.getstate() in current_state_1sec)):
        #print("Closing out Record")  ## DEBUG
        closeOutRecord()     
        lastRecordTime = scantime
        
    # Check current state; either write 1-sec record or accumulate values
    # Note we MAY close out a ~60-sec record AND write a 1-sec record during 
    #  a single scan.  TODO - test this fully
    if (mon.getstate() in current_state_1sec):
        #print("Writing 1sec Record")  ## DEBUG
        write1secRecord()
        lastRecordTime = scantime
    else:
        #    accumulateValues()    # Accumulate values only when not currently in 1-sec ## This should happen until they are closed out.
        ## DWC 01.26 Accumulate pressure values  IDEALLY ALL VALUES SHOULD BE ACCUMULATED AT THIS POINT IN CODE
        Lib.p_sensors[currentpressurevalve].appendValue(currentpressure)
        
    ## Check values:    
    for a in [0,1,2,3]:
        print("Vlv: {:d} " .format(Lib.p_sensors[a].valve),end='')
        try:
            print("Len: {:d} ".format(len(Lib.p_sensors[a].values)),end='')
            ##print("{:d} ".format(len(pressure_item.values)))
            for x in range (len(Lib.p_sensors[a].values)):
                print("{:6.2f}" .format(Lib.p_sensors[a].values[x]),end='' )
        except:
            print("Can't print pressure values using len(pressure_item.values))")
        print("")
 
 
    ## Check Filesize and Decide to create a new File
    try:
        statInfo = os.stat(dataFilename)
        #print "filesize is: ", statInfo.st_size
        dataFileSize = statInfo.st_size
    except:
        print("Unable to read filesize for {}".format(dataFilename))
        dataFileSize = 0
    if dataFileSize > Conf.maxFileSize:
            try: 
                dataFile.close()
            except:
                print("Unable to close old DATA file")
            print("Reached max Data filesize of {} Creating a new file.".format(Conf.maxFileSize))
            dataFilename = Conf.savePath+time.strftime("%Y-%m-%d_%H_%M_%S_",time.gmtime())+BBBsiteName+"_Data.csv"
            print("New file is: {}".format(dataFilename))
            #Record headers to Data File (for Records)
            dataFile = open(dataFilename,'ab')
            dataFile.write(Lib.record(HEADER_REC)+"\n")
            dataFile.close()

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

    executiontime = time.time()-scantimeusec

    
    ## DWC 01.22 move all normal std out to here
    #print("time at top of loop: {}".format(scantime))
    if (math.trunc(scantime % 30)) == 0:
        print(headerString)

    ## DWC 01.24 add valve designations to allow tracking valve positions in std out
    ## Note currentpressurevalve is set when pressure is measured, not updated later
    if   currentpressurevalve == 0:   valvepressname = "0"
    elif currentpressurevalve == 1:   valvepressname = "W"
    elif currentpressurevalve == 2:   valvepressname = "F"
    elif currentpressurevalve == 3:   valvepressname = "Z"
    else:   valvepressname = "-"

    ## DWC 01.24 add valve designations to allow tracking valve positions in std out
    if    valveco2 == 4:   valveCO2name = "W"
    elif valveco2 == 5:   valveCO2name = "F"
    elif valveco2 == 6:   valveCO2name = "R"
    else:   valveCO2name = "-"



    if True:     ## TEST PRINT
        scantimeSTRING = time.strftime("%y-%m-%d %H:%M:%S ",time.gmtime())
        print("{} ".format(scantimeSTRING), end='')    ## % 86400 converts to seconds into GMT day, for testing only
    ## DWC 01.24 insert CO2 valve info (valve name for last value, new valve #, time on new valve
    print("{:s}{:1d}{:2.0f} ".format(valveCO2name, valveco2, co2_elapsed), end='')

    #print("adcCaptureList: {}".format(adcCaptureList))  ## DEBUG
    for item in adcCaptureList:
        print("{:3.0f} " .format(item[1]), end='')
    adcCaptureList = list() # empty list

    ## DWC 01.24 insert pressure valve info (valve name for last value, new valve #, time on new valve
    print(" {:s}{:1d}{:1.0f}".format(valvepressname, valvepress,  press_elapsed), end='')
    print("{:>6.2f} ".format(currentpressure), end='') # local conversion to Pascals, inH2O sensor range +/- 2inH2O

    ## Deliver any xbee values to std out
    for item in xbeeCaptureList:
        print("{:>4.2f} ".format(Decimal(item)),end='')
    ## Cleanup
    xbeeCaptureList = [NaN,NaN,NaN]  ## Reset values after stdout output.

    print("{:1d}{:1d}{:1d} {:1d}{:1d}{:1d}".format(wh.status, whmode, wh.prevMode, f.status, fmode, f.prevMode), end='')
    print(" {:1d}{:1d}".format(mon.state, mon.prevState), end='')
    print (" {:>4.2f}".format(round(Decimal(executiontime),3)), end='')
    
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
