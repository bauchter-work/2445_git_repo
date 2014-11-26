#! /sur/bin/python

# Code used to perform query of BeagleBoneBlack DI's and AI's 
#
# Revision History:
# 2014-02-06 - BDA - Initial codebase


SWversion = "v0.0.1"

import socket, sys, time, struct, traceback
import os
import subprocess
import gobject
from time import strftime, gmtime
import xml.etree.ElementTree as ElementTree
import threading
#Import GPIO interfaces
import Adafruit_BBIO.GPIO as GPIO
import Adafruit_BBIO.ADC as ADC

ADC.setup()

# Load Configuration File
try: 
    import LogConfig
except:
    print "No LogConfig.py file available"
    sys.exit()

#Define variables in local namespace (for declaration of "global" later) 
x = 0
deviceList = ["P9_33","P9_36","P9_35"]  #ADC pins
deviceDescriptions = ["Pot_33","Pot_36","floating_35"]

#define a way to get free space on the storage device
def get_free_space_bytes(folder):
    st = os.statvfs(folder)
    return st.f_bavail * st.f_frsize


def build_dat_file_header():
    headerCSICompatibleStart = "\"TOA5\",\"TI\",\"BeagleBoneBlack\",\"12345\",\"6005A\",\"LogValues\",\"12345\",\""+str(LogConfig.sleepTime)+"_Second_Results\"\r\n\"TIMESTAMP\",\"RECORD\",\"FAILED_QUERIES\""
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

# record some variable names based on time
#DAT Filename
datFilename = strftime("%Y-%m-%d_%H_%M_%S_",gmtime())+LogConfig.siteName+"_scanData.dat"
#Node Addresses Filename
nodeAddressFilename = strftime("%Y-%m-%d_%H_%M_%S_",gmtime())+LogConfig.siteName+"_scanInfo.csv"


#TODO Ping the system for hardware version
#radioModuleFW = str(hex(sysPingList[3]))
#print "Radio Module's Firmware is: ",radioModuleFW

#OPEN a fixed filename for recording the latest generated device_generated-to-device_unique and Custom Name Table
#uniqueNodeAddresses = open(nodeAddressFilename,'wb')
#uniqueNodeAddresses.write("DateTime,Short Address,Long Address,Description,Device,Device Image,Device Firmware Version\r\n")

#Record the firmware version of the Coordinator Software (this can be done via Sys_GetFWVersion and Sys Ping)
#uniqueNodeAddresses.write("SmartenIt System Firmware Version is: "+sysFWList[1]+"\r\n")
#uniqueNodeAddresses.write("Radio Module's Firmware is: "+radioModuleFW+"\r\n")
#uniqueNodeAddresses.write("HarmonyGateway_dbus Version is: "+HGversion+"\r\n")

#Record all user-defined settings into this file
#uniqueNodeAddresses.write("pollRate (delay between commands) is: "+str(LogConfig.pollRate)+" seconds\r\n")
#uniqueNodeAddresses.write("timeoutValue (wait time before query is discarded) is: "+str(LogConfig.timeoutValue)+" seconds\r\n")
#uniqueNodeAddresses.write("sleepTime (time interval for group queries) is: "+str(LogConfig.sleepTime)+" seconds\r\n")
#uniqueNodeAddresses.write("maxRetries (times to retry each query if failed) is: "+str(LogConfig.maxRetries)+" retries\r\n")
#uniqueNodeAddresses.write("maxFileSize (max bytes for each ScanData File) is: "+str(LogConfig.maxFileSize)+" Bytes\r\n")
#uniqueNodeAddresses.write("useFTP setting is: "+str(LogConfig.useFTP)+"\r\n")
if LogConfig.useFTP:
    uniqueNodeAddresses.write("ftpURL setting is: "+str(LogConfig.ftpURL)+"\r\n")
    uniqueNodeAddresses.write("ftpUser setting is: "+str(LogConfig.ftpUser)+"\r\n")
    uniqueNodeAddresses.write("ftpPath setting is: "+str(LogConfig.ftpPath)+"\r\n")
    uniqueNodeAddresses.write("ftpUpload Interval is every: "+str(LogConfig.ftpUploadInterval)+" minutes\r\n")

#uniqueNodeAddresses.close()

#print "Writing of session specific values is complete."


#FTP Upload the NodeAddresses File
if LogConfig.useFTP: 
    try:
       #print "lftp -c \"open -u "+LogConfig.ftpUser+","+LogConfig.ftpPassword+" "+LogConfig.ftpURL+"; cd "+LogConfig.ftpPath+"; put "+nodeAddressFilename+";\""
       return_code = subprocess.call("lftp -c \"open -u "+LogConfig.ftpUser+","+LogConfig.ftpPassword+" "+LogConfig.ftpURL+"; cd "+LogConfig.ftpPath+
                      "; put "+nodeAddressFilename+";\"", shell=True)
    except:
        print "FTP Upload of ",nodeAddressFilename," Failed.  Check LogConfig settings and/or system settings(firewalls, port forwards,etc.), that lftp is installed..."
    print "FTP Upload Return_Code is: ",return_code

#Build CSI Compatible Header File
build_dat_file_header()

######################---MAIN--QUERY--LOOP---#########################

loopCount = 1
recNum = 0
failedQueries = 0

ftpStartTime = time.time()  #Start a time capture for periodically uploading data to an FTP Server

#frame the initial remote FTP file
if LogConfig.useFTP:
    try:
        ftpArgs = "lftp "+"-c "+'"'+"open -u "+LogConfig.ftpUser+","+LogConfig.ftpPassword+" "+LogConfig.ftpURL+"; cd "+LogConfig.ftpPath+"; put -c "+datFilename+";"+'"'
        #print ftpArgs
        pid = subprocess.Popen(ftpArgs,shell=True)  #default is shell=False
    except:
        print "FTP Upload of ",datFilename," Failed.  Check LogConfig settings and/or system settings(firewalls, port forwards,etc.), that lftp is installed..."
        print "FTP Upload Process ID is: ",pid

#Wait until time is a unit of the sampling interval
print "Time is: ",time.time()," Waiting for a clean interval of",LogConfig.sleepTime,"seconds before starting..."

while (int((time.time()*100)) % int((LogConfig.sleepTime*100))) != 0:
    #print "Time is: ",time.time(),".  Waiting..."
    time.sleep(0.01)
print "Starting Data Capture...\r\n\r\n"

#Header of STDIO:
outputHeader = "UTC Time, RecNum, Description, Voltage, TimeDelta"
# Output Header Column
print outputHeader

            
# the loopCount should run until the device is out of memory
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
    if datFileSize > LogConfig.maxFileSize:
            try: 
                datFile.close()
            except:
                print "Unable to close old DAT file"
            print "Reached max Dat filesize of", LogConfig.maxFileSize,"  Creating a new file."
            datFilename = strftime("%Y-%m-%d_%H_%M_%S_",gmtime())+LogConfig.siteName+"_scanData.dat"
            print "New filename is: ", datFilename
            build_dat_file_header()
            
    datFile = open(datFilename,'ab')
    loopStartTime = time.time()
    #print "Loop Start Time: ",loopStartTime
    for x in range(len(deviceList)):
        recNum +=1
        retries = 0
        #READ PINS
        Value = ADC.read(deviceList[x])
	Voltage = Value*1.8
	#print "Voltage is: ",Voltage," volts"
        
        #TODO Now it may (or may not be) wise to do some bounds checking or verification that all values have been acquired
        
        #Store these values to the Dat File output...  
        #print only the interesting information per the outputHeader
        print strftime("\"%Y-%m-%d %H:%M:%S\"",gmtime())+","+str(recNum)+","+deviceDescriptions[x]+","+str(Voltage)+","+str("%.2f" % (time.time()-loopStartTime))
        if x == 0:
            datFile.write(strftime("\"%Y-%m-%d %H:%M:%S\"",gmtime())+","+str(recNum)+","+str(failedQueries)+","+str(Voltage)+","+str(time.time()-loopStartTime))
        else:
            datFile.write(","+str(Voltage)+","+str(time.time()-loopStartTime))
        time.sleep(LogConfig.pollRate)
    loopEndTime = time.time()
    datFile.write(","+str(loopEndTime-loopStartTime)+"\r\n")
    print "" #just insert a spacer
    #print "Loop End Time: ",loopEndTime
    while ((loopEndTime - loopStartTime) < LogConfig.sleepTime) and ((int((time.time()*100)) % int((LogConfig.sleepTime*100))) != 0):
        time.sleep(0.01)     #wait for next scan interval
        loopEndTime = time.time()
    if ((time.time() - ftpStartTime)/60 > LogConfig.ftpUploadInterval) and LogConfig.useFTP:
        try:
            ftpArgs = "lftp "+"-c "+'"'+"open -u "+LogConfig.ftpUser+","+LogConfig.ftpPassword+" "+LogConfig.ftpURL+"; cd "+LogConfig.ftpPath+"; put -c "+datFilename+";"+'"'
            #print ftpArgs
            pid = subprocess.Popen(ftpArgs,shell=True)  #default is shell=False
        except:
            print "FTP Upload of ",datFilename," Failed.  Check LogConfig settings and/or system settings(firewalls, port forwards,etc.), that lftp is installed..."
            print "FTP Upload Process ID is: ",pid
        ftpStartTime = time.time()  #reset start time

    # Check how much free space is on the drive
    freeDiskSpace = get_free_space_bytes("/home")
    #print "There's this much free space: ",freeDiskSpace
    
try: 
    datFile.close()
except:
    print "Unable to close the DAT file currently being used"
    
print "Free Disk Space has exceeded an allowable level.  Quitting program to preserve existing data..."
