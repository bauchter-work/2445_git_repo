#! /sur/bin/python

# Code used to perform query of BeagleBoneBlack with ADC1115 attached 
#
# Revision History:
# 2014-06-30 - BDA - Initial codebase
# 2014-07-02 - BDA - Changed SPS to 8

SWversion = "v0.0.1"

import socket, sys, time, struct, traceback
import os
import subprocess
import gobject
from time import strftime, gmtime
import xml.etree.ElementTree as ElementTree
import threading
import signal
from Adafruit_ADS1x15 import ADS1x15

#Define variables in local namespace (for declaration of "global" later) 
x = 0
deviceList = ["0","1"]  #ADC pins
deviceDescriptions = ["ADC_AIN0","ADC_AIN1"]
pinGain = [ 4096, 256 ]
pinSPS = [ 8, 8 ]

ADS1115 = 0x01 # 16-bit ADC
# gain = 1024
# sps = 8


def build_dat_file_header():
    headerCSICompatibleStart = "\"TOA5\",\"TI\",\"BeagleBoneBlack\",\"12345\",\"6005A\",\"LogValues\",\"12345\",\"5_Second_Results\"\r\n\"TIMESTAMP\",\"RECORD\",\"FAILED_QUERIES\""
    headerCSICompatibleMiddle = "\"TS\",\"RN\",\"FQ\""
    headerCSICompatibleEnd = "\"\",\"\""

    for x in range(len(deviceList)):
        headerCSICompatibleStart = headerCSICompatibleStart+",\"Voltage_"+deviceDescriptions[x]+"\",\"TimeDelta_"+deviceDescriptions[x]+"\""

    headerCSICompatible = headerCSICompatibleStart+",\"ScanDuration\""+"\r\n"


    # Initialize CSI-compatible output file
    datFile = open(datFilename,'ab')
    datFile.write(headerCSICompatible)
    datFile.close()
    return


#Initialize ADC
adc = ADS1x15(ic=ADS1115)

# record some variable names based on time
#DAT Filename
datFilename = strftime("%Y-%m-%d_%H_%M_%S_",gmtime())+"ADC1115_scanData.dat"
#Node Addresses Filename
nodeAddressFilename = strftime("%Y-%m-%d_%H_%M_%S_",gmtime())+"ADC1115_scanInfo.csv"

build_dat_file_header()

######################---MAIN--QUERY--LOOP---#########################

loopCount = 1
recNum = 0
failedQueries = 0


#Wait until time is a unit of the sampling interval
print "Time is: ",time.time()," Waiting for a clean interval of 5 seconds before starting..."

while (int((time.time()*100)) % int((5*100))) != 0:
    #print "Time is: ",time.time(),".  Waiting..."
    time.sleep(0.01)
print "Starting Data Capture...\r\n\r\n"

#Header of STDIO:
outputHeader = "UTC Time, RecNum, Description, Voltage, TimeDelta"
# Output Header Column
print outputHeader

            
Voltage = 0
while True:
    # Check the filesize of the datFile
    try:
        statInfo = os.stat(datFilename)
        #print "filesize is: ", statInfo.st_size
        datFileSize = statInfo.st_size
    except:
        print "Unable to read filesize for ", datFilename
        datFileSize = 0
    if datFileSize > 10000000:
            try: 
                datFile.close()
            except:
                print "Unable to close old DAT file"
            print "Reached max Dat filesize of", 10000000 ,"  Creating a new file."
            datFilename = strftime("%Y-%m-%d_%H_%M_%S_",gmtime())+"ADC1115_scanData.dat"
            print "New filename is: ", datFilename
            build_dat_file_header()
            
    datFile = open(datFilename,'ab')
    loopStartTime = time.time()
    #print "Loop Start Time: ",loopStartTime
    for x in range(len(deviceList)):
        recNum +=1
        retries = 0
        #READ CHANNELS, Single Ended, from ADC Chip
        Value = adc.readADCSingleEnded(int(deviceList[x]),pinGain[x],pinSPS[x])
        Value = adc.readADCSingleEnded(int(deviceList[x]),pinGain[x],pinSPS[x])
        Voltage = Value / 1000
        #print "Voltage is: %.8f" % (Voltage)," volts"
        print "X is: ", x, " AIN",deviceList[x]," Gain: ",pinGain[x], " SPS: ",pinSPS[x]
        
        #Store these values to the Dat File output...  
        #print only the interesting information per the outputHeader
        print strftime("\"%Y-%m-%d %H:%M:%S\"",gmtime())+","+str(recNum)+","+deviceDescriptions[x]+","+str(Voltage)+","+str("%.8f" % (time.time()-loopStartTime))
        if x == 0:
            datFile.write(strftime("\"%Y-%m-%d %H:%M:%S\"",gmtime())+","+str(recNum)+","+str(failedQueries)+","+str(Voltage)+","+str(time.time()-loopStartTime))
        else:
            datFile.write(","+str(Voltage)+","+str(time.time()-loopStartTime))
        time.sleep(0)
    loopEndTime = time.time()
    datFile.write(","+str(loopEndTime-loopStartTime)+"\r\n")
    print "" #just insert a spacer
    #print "Loop End Time: ",loopEndTime
    while ((loopEndTime - loopStartTime) < 5) and ((int((time.time()*100)) % int((5*100))) != 0):
        time.sleep(0.01)     #wait for next scan interval
        loopEndTime = time.time()

    
try: 
    datFile.close()
except:
    print "Unable to close the DAT file currently being used"
    
print "Free Disk Space has exceeded an allowable level.  Quitting program to preserve existing data..."
