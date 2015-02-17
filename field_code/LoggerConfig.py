#! /usr/bin/python
# Configuration Information for BeagleBone Black datalogging

siteName = "none"      ## Site names should be STATE_number like "MN_08" or "IL_02", in quotes.  
                       ## Increment the number for each new site.  DO NOT use spaces or special characters.  

co_calib_value = 1700  ## replace with device-specific calibration number. 
                       ## Default = 1700 - no surrounding quotes

waterHeaterIsPresent = True ## type True or False - no surrounding quotes

furnaceIsPresent = True     ## type True or False - no surrounding quotes


xBeeNode1 = "0xffff"   ## Node 1, use "0xffff" if not deployed - include quotes
xBeeNode1Type = "none" ## type "CT", "Pressure", "Door", "none" - incl. quotes   

xBeeNode2 = "0xffff"   ## Node 2, use "0xffff" if not deployed - incl. quotes
xBeeNode2Type = "none" ## type "CT", "Pressure", "Door", "none" - incl. quotes

xBeeNode3 = "0xffff"   ## Node 3, use "0xffff" if not deployed - incl. quotes
xBeeNode3Type = "none" ## type "CT", "Pressure", "Door", "none" - incl. quotes


## This port number is generally NOT CHANGED during field setup
reverseSSHport = 7000  ## Site specific port for contacting remotely

## Default Settings - DO NOT CHANGE ##
savePath = "/srv/field-research/data/" ## location to store data on BBB - Don't Change This
maxFileSize = 750000000  ## Maximum data filesize before creating a new data file (don't exceed 1GB)


