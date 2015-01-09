#! /usr/bin/python

# Configuration Information for BeagleBone Black datalogging
# 2014-10-28 BDA - Initial draft
# 2014-11-12 BDA - Brought out Config items from LoggerMain.py

siteName = "none"           ## Give your site a unique Name (this will be embedded in the output files)
                            ## DO NOT use spaces or special characters.  Underscores are fine.
                            ## This name is correlated to a unique hardware attribute

waterHeaterIsPresent = True ## True or False - update if present
furnaceIsPresent = True     ## True or False
xBeeNode1 = "0x6dfe"   ## Declare End Node addresses for deployed xBee sensors (last 4 hex digits 
                       ##  in the long address of the xbee.
xBeeNode1Type = "CT"   ## type "CT", "Pressure", "Door", "none"    THESE ARE CASE SENSITIVE!

xBeeNode2 = "0xffff"   ## Node 2, use "0xffff" if not deployed
xBeeNode2Type = "none" ## type "CT", "Pressure", "Door", "none"     THESE ARE CASE SENSITIVE!

xBeeNode3 = "0xffff"   ## Node 3, use "0xffff" if not deployed
xBeeNode3Type = "none" ## type "CT", "Pressure", "Door", "none"     THESE ARE CASE SENSITIVE!

co_calib_value = 1700  ## replace with device-specific calibration number. Default = 1700

savePath = "/root/data/" ## location to store data on BBB

maxFileSize = 750000000  ## Maximum data filesize before creating a new data file (don't exceed 1GB)


