#! /usr/bin/python

## LoggerMain -- Combustion Minitoring logic
##
## 2014-11-05 TimC - Initial
## 2014-11-16 TimC - moved setups to library; 
## 2014-11-17 TimC - first cut at state selection logic
## 2014-11-18 TimC - changed mon.state to property, added prevState; cleanup state selection; added example gpio get
## 2014-11-20 BenA - sidestepping some issues with the ADC library for now; using Adafruit library until understood
## 2014-11-24 BenA - added watchdog, config file query, uniqueID, gpio setup, pressure read

import time, math, random, sys, os
from decimal import *
import LoggerLib as Lib
from Adafruit_ADS1x15_mod import ADS1x15 
from xbee import XBee
import serial


###########################################################################################
## setup / initialize

# Activate watchdog
try:
    watchdog = open("/dev/watchdog",'w+')
    watchdog.write("\n")
except:
    print("Unable to access watchdog")

#Get UniqueID for BBB
try:
    os.system("/root/field-code/getUniqueID.sh") #run this to extract Serial Number for EEPROM
    uniqueFile = open("uniqueID",'r')
    uniqueID = uniqueFile.readline().rstrip('\n')
    #print "BBB unique ID is {}".format(uniqueID)
except:
    print("Error retrieving UniqueID from BBB EEPROM")

# Load Configuration File
try: 
    import LoggerConfig as Conf
    siteName = Conf.siteName

except:
    print "No LoggerConfig.py file available or error parsing"
    sys.exit()

#setup all General Purpose Inputs and Outputs
for control in Lib.controls:
    control.setValue(0) #write GPIO.LOW
#print("GPI {}: reads {}".format(Lib.sw1.name,Lib.sw1.getValue() ))
#print("GPI {}: reads {}".format(Lib.sw2.name,Lib.sw1.getValue() ))

#Turn on 24V power
for control in Lib.controls:
    if control.name == "24V@P8-15":
        control.setValue(1) #write GPIO.HIGH

#TODO Setup/clear UART buffer?
ser = serial.Serial(port="/dev/tty4",baudrate=9600, timeout=1)
#xbee = XBee(ser)
while True:
    try:
        print ("xbee reads: {}".format(ser.read(100)))
    except KeyboardInterrupt:
        break

## set furnace and waterhtr TCs
if True:
    for sensor in Lib.tcs:
        if sensor.name == "TC1@U11":
            Lib.furnace.tc = sensor
            break

    for sensor in Lib.tcs:
        if sensor.name == "TC2@U11":
            Lib.waterHtr.tc = sensor
            break

ADS1115=0x01 #Defined for Adafruit ADC Library


###########################################################################################
## smoke tests / sanity checks
if False: ## TODO: needs update
    print("decimal."), 
    print(getcontext()) ## for module decimal 

    print("class Adc {}".format(Lib.Adc.__doc__)) ## https://docs.python.org/2/library/inspect.html
    for item in Lib.adcs:
        print("adc: {}  bus: {}  addr: 0x{:02x}".format(item.name, item.bus, item.addr))

    print
    for item in Lib.sensors:
        if isinstance(item, Lib.Ain):
            print("ain: {}  bus: {}  addr: 0x{:02x}  gain: {}  sps: {}  mux: {}"
                .format(item.name, item.adc.bus, item.adc.addr, item.adc.gain, item.adc.sps, item.mux))
        elif isinstance(item, Lib.Gpi):
            print("gpi: {}  pin: {}  ".format(item.name, item.pin))
        elif isinstance(item, Lib.Ser):
            print("sio: {}  uart: {}  ".format(item.name, item.uart))
        else:
            print("unk: {}  ???  ".format(item.name))

    for control in Lib.controls:
        print("control: {}  pin: {}  ".format(control.name, control.pin))

###########################################################################################
## local functions

def get_free_space_bytes(folder):
    #command to check remaining free space on the storage device
    st = os.statvfs(folder)
    return st.f_bavail * st.f_frsize
    pass

def fetchCO2():
    pass

def fetchTempsAdafruit(ADCs):
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
                        if (sensor.adc.i2cIndex == ADC.busnum) \
                         and (sensor.adc.addrs[sensor.adcIndex] == ADC.address) \
                         and (sensor.mux == mux):
                            if (sensor.name == "TC15@U15") or (sensor.name == "TC16@U15"):
                                result = (360*(Volts-0.5))+32 #for deg. F
                                #print sensor.name, "reads ", result, "F"
                                #print "I2C Address: ",sensor.adc.addrs[sensor.adcIndex],"AIN:",sensor.mux
                            else:
                                result = (360*Volts)+32 #for deg. F, 0V bias
                                #print sensor.name, "reads ", ((360*(Volts))+32), "F"
                                #print("I2C Address: 0x{:02x}, AIN: {},I2Cindex: {}" \
                                #  .format(sensor.adc.addrs[sensor.adcIndex],sensor.mux, sensor.adc.i2cIndex))
                            #result = random.random() * 200.0 ## DBG
                            sensor.appendAdcValue(result)
    pass

def fetchTemps():    #NOTE DO NOT USE RIGHT NOW (will execute, but Provides Unreliable Data)
    for mux in range(Lib.Adc.NMUX):
        for job in range(3): ## [ start, sleep, fetch ]
            for sensor in Lib.sensors:
                if isinstance(sensor, Lib.Tc) and sensor.mux == mux:
                    adc = sensor.adc
                    if (job == 0): ## start
                        adc.startAdc(mux,sps=8)
                        adc.startTime = time.time() ## DBG
                    elif (job == 1): ## sleep
                        elapsed = time.time() - adc.startTime 
                        adctime = (1.0 / adc.sps) + .001 
                        if (elapsed < adctime):
                            #print("fetching 0x{:02x} too early: at {} sps delay should be {} but is {}"\
                            #        .format(adc.addr, sensor.sps, adctime, elapsed))
                            time.sleep(adctime - elapsed + .002)
                    else: #if (job == 2): ## fetch
                        result = adc.fetchAdc()
                        print("{} \tResult: {}V, Gain:{}, I2C Address: 0x{:02x},Input:{}"\
                            .format(sensor.name,result,adc.pga,adc.addrs[sensor.adcIndex],sensor.mux))
                        sensor.appendAdcValue(result)
    pass

def fetchPressure():
    #Read Pressure sensor check
    pressureAvg = 0.0
    count = 0
    for i in range(25):
        previous = time.time()
        pressure_inH20 = Lib.dlvr.readPressure()
        if math.isnan(pressure_inH20):
            count -=1
        else:
          #print "Pressure is: {}".format(pressure_inH20),
          #print "time delay is: {}".format(time.time()-previous)
          pressureAvg = pressureAvg + pressure_inH20
        count += 1
        time.sleep(0.0066-(time.time()-previous)) #pressure is updated every 9.5mSec for low power
                                  #The delay between adc updates is 6 m sec 
                                  #for 31 cycles then it does an internal 
                                  #check that takes 9.5. We should go just over 6 for our delay 
                                  #and may get a duplicate reading occasionally. 

    if count != 0.0:
        pressureAvg = pressureAvg/count
    #print "count is: {}".format(count),
    #print "pressureAvg is: {}".format(pressureAvg)
    return pressureAvg
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
        self.__state = None #= Mon.State6Off ## TODO?

    def getprevState(self): return self.__prevState
    def setprevState(self, value): self.__prevState = value
    def delprevState(self): del self.__prevState
    prevState = property(getprevState, setprevState, delprevState, "'prevState' property")

    def getstate(self): return self.__state
    def setstate(self, value): 
        self.__prevState = self.__state
        self.__state = value
        pass
    def delstate(self): del self.__state
    state = property(getstate, setstate, delstate, "'state' property")


#############
## start main
#############
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

## determine the current state
#fetchTemps()
fetchTempsAdafruit([AdaAdcU11,AdaAdcU13,AdaAdcU14,AdaAdcU15]) #grab all ADC inputs from TC ADCs 

## main loop
Lib.Timer.start()
Lib.Timer.sleep()
while True:
    ## Capture time at top of second
    tick = Lib.Timer.stime()
    #print("time at top of loop: {}".format(tick))

    ## Scan all inputs
    #fetchTemps() ## commented for DBG
    fetchTempsAdafruit([AdaAdcU11,AdaAdcU13,AdaAdcU14,AdaAdcU15])
    
    #Read Pressure sensor check
    for sensor in Lib.sensors:
        if sensor.name == "DLVR@U12":
            sensor.appendValue(fetchPressure()) #TODO - do this right away or in Pressure Control?
    #print "Pressure is: {}".format(fetchPressure()) #read full 25 samples
    
    #One debug output for a TC:
    #for sensor in Lib.tcs:
    #    if sensor.name=="TC1@U11":
    #        print("TC1@U11 reads: {}".format(sensor.getMostRecentValue()))
                
    #for burner in Lib.burners:
    #    burner.tc.appendAdcValue(random.random() * 200.0) ## added for DBG

    ## Process data
    ## Determine status of both burners
    ## Assign operating mode of wh and furnace
    whmode = wh.mode()
    fmode = f.mode()
    print("time {:>12.1f} furnace temp: {:>5.1f}  status: {}  mode: {}  mon state: {}  prevState: {}  sw1: {}"\
            .format(tick, f.tc.getMostRecentValue(), f.status(), fmode, mon.state, mon.prevState, Lib.sw1.getValue()))

    ## Assign monitoring system state [these need to be re-checked thoroughly--TimC]
    if ((whmode == Lib.Burner.Mode2On) or (fmode == Lib.Burner.Mode2On)): 
        ## at least one burner already on
        mon.state = Mon.State2On
    elif ((whmode == Lib.Burner.Mode1JustStarted) or (fmode == Lib.Burner.Mode1JustStarted)): 
        ## first burner just started [this is _either_ burner just started, right?--TimC]
        mon.state = Mon.State1Start
    elif ((whmode == Lib.Burner.Mode3JustStopped) or (fmode == Lib.Burner.Mode3JustStopped)): 
        ## last burner just stopped
        mon.state = Mon.State3Stop
    elif ((mon.state == Mon.State4CoolDown) or (whmode == Lib.Burner.Mode4Cooling) or (fmode == Lib.Burner.Mode4Cooling)): 
        ## hold in state 4 even if burners have moved to state 5
        lastStopTime = f.stopTime if (wh.stopTime < f.stopTime) else wh.stopTime
        if ((((tick - lastStopTime) >= 120.0) and (datetime.utcfromtimestamp(tick).second == 0)) or (lastStopTime >= 180.0)): 
            ## only switch state at top of minute  ## check for overrun
            mon.state = Mon.State6Off
        else: ## change from state 3 to 4 (or stay in state 4)
            mon.state = Mon.State4CoolDown
    elif (mon.state == Mon.State6Off):
        if ((math.trunc(tick) % 900) < 60): ## in first minute of 15 minute interval
            ## TODO set flag to start CO2 measurement
            mon.state = Mon.State5OffCO2
        ## else no change
    elif (mon.state == Mon.State5OffCO2):
        if ((math.trunc(tick) % 900) >= 60): ## beyond first minute of 15 minute interval 
            mon.state = Mon.State6Off
        ## else no change
    else:
        print("no state change")

    #for sensor in Lib.sensors:
	#	print sensor.name
    		       
    ## Pressure control routine
    ## CO2 control routine
    ## Set valve and pump control ports to state required for following scan

    ## Record control


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

