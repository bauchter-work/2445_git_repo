#! /sur/bin/python

# Code used to perform logging of Combustion Spillage system based off of 
# BeagleBoneBlack (Rev. C) DI's and AI's and a custom Sensor Board.
# The program relies on a separate file called "LoggerConfig.py" to store
# most fixed values for this system.
#
# The sensor board design files are available in:
# P:\PROJECTS\Proj_Ben_Auchter\2445\Sensor_Board_Design
# 
# Revision History:
# 2014-10-28 - BDA - Initial codebase skeleton
#
SWversion = "v0.0.1"


##### IMPORT LIBRARIES #####
import socket, sys, time, struct, traceback, signal
import os
import subprocess
from time import strftime, gmtime
#Import GPIO interfaces
import Adafruit_BBIO.GPIO as GPIO
#import Adafruit_BBIO.ADC as ADC
from Adafruit_ADS1x15_mod import ADS1x15

# Load Configuration File
try: 
    import LoggerConfig
except:
    print "No LoggerConfig.py file available"
    sys.exit()


##### PERFORM HARDWARE SETUP #####
## Setup the ADC's
ADS1115 = 0x01	# 16-bit ADC

# Initialise the ADCs using explicit bus numbers
adcU8 =  ADS1x15(address = 0x48, ic=ADS1115, busnum = 1) #busnum = 1 is P9_Pin19_I2C2_SCL and P9_Pin20_I2C2_SDA
adcU9 =  ADS1x15(address = 0x49, ic=ADS1115, busnum = 1)
adcU10 = ADS1x15(address = 0x4A, ic=ADS1115, busnum = 1)

adcU11 = ADS1x15(address = 0x48, ic=ADS1115, busnum = 2) #busnum = 2 is P9_Pin17_I2C1_SCL and P9_Pin18_I2C1_SDA
adcU13 = ADS1x15(address = 0x49, ic=ADS1115, busnum = 2)
adcU14 = ADS1x15(address = 0x4A, ic=ADS1115, busnum = 2)
adcU15 = ADS1x15(address = 0x4B, ic=ADS1115, busnum = 2)

#TODO - set up all pinouts as necessary before any operation


##### Function Declarations #####

def find_burner_status():
    #This function determines whether the water heater is turned on or off
    #Set values for st_wh_brnr, st_furn_brnr
    
    # TODO
    #  [Will look at how much temp has changed over last second, 
    #  and how much it has changed over last second compared to a running average of the
    #  previous N seconds; a fast increse means a startup, a large decrease from running 
    #  average means a shutdown.]
    
    #Determine whether furnace burner has turned on or off
    #If a burner status has changed, set new value for st_wh_brnr or st_furn_brnr
    return

def cycle_ctrl():
    #Call with prior value of st_ctrl 
    #Set new st_ctrl based on burner status, status change, and time 
    #TODO
    return

def measure_pressure():
    #Measures pressure, if required per value of st_ctrl
    #Query DLVR dP sensor 25 times at 7 msec interval, 175 msec total
    #[Would be great if this could be done as a backgrond operation, 
    #but if not, we'll adjust the number of queries to allow code to run]
    #Accumulate & calculate count, average, max, min & SD for each scan, will
    #build an overall avg, max, min, SD for the whole cycle when we write data.
    
    #TODO
    
    return
    
def measure_CO2():
    #[Measure CO2, if required per value of st_ctrl]
    #read analog input once
    #TODO
    return

def measure_temperatures():
    # TODO Read all temperatures
    ## READ ADCs ##
    global adcU8_voltage, adcU9_voltage, adcU10_voltage
    global adcU11_voltage, adcU13_voltage, adcU14_voltage, adcU15_voltage
    
    #adcU8:
    for x in range(0,4):
        Value = adcU8.readADCSingleEnded(0,LoggerConfig.adcU8_gain[x],LoggerConfig.adcU8_sps[x])
        Value = adcU8.readADCSingleEnded(0,LoggerConfig.adcU8_gain[x],LoggerConfig.adcU8_sps[x])
        adcU8_voltage[x] = Value / 1000
        print "adcU8, AIN ",x,", reads: %.6f volts" % (adcU8_voltage[x])
    
    #adcU9
    for x in range(0,4):
        Value = adcU9.readADCSingleEnded(0,LoggerConfig.adcU9_gain[x],LoggerConfig.adcU9_sps[x])
        Value = adcU9.readADCSingleEnded(0,LoggerConfig.adcU9_gain[x],LoggerConfig.adcU9_sps[x])
        adcU9_voltage[x] = Value / 1000
        print "adcU9, AIN ",x,", reads: %.6f volts" % (adcU9_voltage[x])
    
    #adcU10
    for x in range(0,4):
        Value = adcU10.readADCSingleEnded(0,LoggerConfig.adcU10_gain[x],LoggerConfig.adcU10_sps[x])
        Value = adcU10.readADCSingleEnded(0,LoggerConfig.adcU10_gain[x],LoggerConfig.adcU10_sps[x])
        adcU10_voltage[x] = Value / 1000
        print "adcU10, AIN",x,", reads: %.6f volts" % (adcU10_voltage[x])
    #TODO adcU11
    #TODO adcU13
    #TODO adcU14
    #TODO adcU15
    
    #TODO Now it may (or may not be) wise to do some bounds checking or verification that all values have been acquired
        
    return

def get_free_space_bytes(folder):
    #command to check remaining free space on the storage device
    st = os.statvfs(folder)
    return st.f_bavail * st.f_frsize

#Creates the basic file header.  Assumes datFileName is defined.
def build_dat_file_header():
    headerCSICompatibleStart = "\"TOA5\",\"TI\",\"BeagleBoneBlack\",\"Rev_C\",\"2445A\",\"LoggerProgram\",\""+SWversion+"\",\""+str(LoggerConfig.scanTime)+"_Second_Results\"\r\n\"TIMESTAMP\",\"RECORD\""
    headerCSICompatibleMiddle = "\"TS\",\"RN\",\"FQ\""
    headerCSICompatibleEnd = "\"\",\"\""

    for x in range(len(LoggerConfig.deviceList)):
        headerCSICompatibleStart = headerCSICompatibleStart+",\"Voltage_"+LoggerConfig.deviceDescriptions[x]+"\",\"TimeDelta_"+LoggerConfig.deviceDescriptions[x]+"\""

    headerCSICompatible = headerCSICompatibleStart+",\"ScanDuration\""+"\r\n"


    # Initialize CSI-compatible output file
    datFile = open(datFilename,'ab')
    datFile.write(headerCSICompatible)
    datFile.close()
    return


##### DEFINE VARIABLES  #####

#Define variables in local namespace (for declaration of "global" later) 
x = 0
st_wh_burner = 0   #status of water heater burner (0,1, or better 0 - 3, current and prior status)
st_furn_burner = 0 #status of furnace burner (like wh status)
state_ctrl = 0     # control cycle state (integer)
    # [st_ctrl includes information on burner state, valve positions, pump status, etc
    # and is updated each second.]

#DAT Filename, based on time
datFilename = strftime("%Y-%m-%d_%H_%M_%S_",gmtime())+LoggerConfig.siteName+"_scanData.dat"
#TODO Diagnostics Filename
diagnosticsFilename = strftime("%Y-%m-%d_%H_%M_%S_",gmtime())+LoggerConfig.siteName+"_scanInfo.csv"

recNum = 0   # Establish first Record Number (to be incremented each scan)

#ADC Output storage
adcU8_voltage  = [0.0,0.0,0.0,0.0]
adcU9_voltage  = [0.0,0.0,0.0,0.0]
adcU10_voltage = [0.0,0.0,0.0,0.0]
adcU11_voltage = [0.0,0.0,0.0,0.0]
adcU13_voltage = [0.0,0.0,0.0,0.0]
adcU14_voltage = [0.0,0.0,0.0,0.0]
adcU15_voltage = [0.0,0.0,0.0,0.0]

build_dat_file_header()  #Build CSI Compatible Header File and write it into datFilename

######################---MAIN--QUERY--LOOP---#########################

#Wait until time is a unit of the sampling interval
print "Time is: ",time.time()," Waiting for a clean interval of",LoggerConfig.scanTime,"seconds before starting..."

while (int((time.time()*100)) % int((LoggerConfig.scanTime*100))) != 0:
    #print "Time is: ",time.time(),".  Waiting..."
    time.sleep(0.01)
print "Starting Data Capture...\r\n\r\n"

#Header of STDIO:
outputHeader = "UTC Time, RecNum, Description, Voltage, TimeDelta"
# Output Header Column
print outputHeader

            
# the loop should run until the device is out of memory
# TODO Then notify managers of the site?  Loop back over??
datFileSize = 0
freeDiskSpace = get_free_space_bytes("/home")
Voltage = 0
while freeDiskSpace > 1000000:
    # Check the filesize of the datFile
    try:
        statInfo = os.stat(datFilename)
        #print "filesize is: ", statInfo.st_size
        datFileSize = statInfo.st_size
    except:
        print "Unable to read filesize for ", datFilename
        datFileSize = 0
    if datFileSize > LoggerConfig.maxFileSize:
            try: 
                datFile.close()
            except:
                print "Unable to close old DAT file"
            print "Reached max Dat filesize of", LoggerConfig.maxFileSize,"  Creating a new file."
            datFilename = strftime("%Y-%m-%d_%H_%M_%S_",gmtime())+LoggerConfig.siteName+"_scanData.dat"
            print "New filename is: ", datFilename
            build_dat_file_header()
            
    datFile = open(datFilename,'ab')
    loopStartTime = time.time()
    #print "Loop Start Time: ",loopStartTime
    recNum +=1
    
    ##### PERFORM UP Front Reads #####
    measure_temperatures()   #Read all temperatures

    find_burner_status() #Call function find_burner_status; Decide whether either burner has started or stopped
    cycle_ctrl()         #Call function cycle_ctrl; Decide where the code is placed in the timed measurement cycle, change as needed, set up for next measurements
    
    #TODO, IF Required per value of st_ctrl
    measure_pressure()
    #TODO, IF Required per value of st_ctrl
    measure_CO2()
    
    #Set up for next measurement cycle
    #TODO [Set GPIO line states for next cycle.  Should be done here to provide max time before next 1-sec scan]
    
    #Accumulate values
    #TODO [Accumulate current measurement values to get averages, etc.
    #When st_ctrl indicates the end of a measurement period, calculate averages, reset accumulators]
    
    #Write data
    #TODO [Depends on st_ctrl.  If called for, take values, averages, etc from above, write data record to file]
    #Store these values to the Dat File output...  
    #print only the interesting information per the outputHeader
    print strftime("\"%Y-%m-%d %H:%M:%S\"",gmtime())+","+str(recNum)+","+LoggerConfig.deviceDescriptions[x]+","+str(Voltage)+","+str("%.2f" % (time.time()-loopStartTime))
    #if x == 0:
    #    datFile.write(strftime("\"%Y-%m-%d %H:%M:%S\"",gmtime())+","+str(recNum)+","+str(Voltage)+","+str(time.time()-loopStartTime))
    #else:
    #    datFile.write(","+str(Voltage)+","+str(time.time()-loopStartTime))
    
    #Other
    #TODO [Time checks, R-sync, write diagnostic info, etc
    #some of this, in particular R-sync management, will ideally happen in background]
    
    
    loopEndTime = time.time()
    datFile.write(","+str(loopEndTime-loopStartTime)+"\r\n")
    print "" #just insert a spacer
    #print "Loop End Time: ",loopEndTime
    
    #Wait for next scan cycle
    while ((loopEndTime - loopStartTime) < LoggerConfig.scanTime) and ((int((time.time()*100)) % int((LoggerConfig.scanTime*100))) != 0):
        time.sleep(0.01)     #wait for next scan interval
        loopEndTime = time.time()

    # Check how much free space is on the drive
    freeDiskSpace = get_free_space_bytes("/home")
    #print "There's this much free space: ",freeDiskSpace
    
try: 
    datFile.close()
except:
    print "Unable to close the DAT file currently being used"
    
print "Free Disk Space has exceeded an allowable level.  Quitting program to preserve existing data..."

#TODO Email or SMS a notification?
