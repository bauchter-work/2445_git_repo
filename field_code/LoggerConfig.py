#! /usr/bin/python

# Configuration Information for BeagleBone Black datalogging
# 2014-10-28 BDA - Initial draft
# 2014-11-12 BDA - Brought out Config items from LoggerMain.py

siteName = "bbbMPLS"        #Give your site a unique Name (this will be embedded in the output files)
                            #Don't use spaces or special characters.  Underscores are fine.
			                #This name is correlated to a unique hardware attribute
waterHeaterIsPresent = True #True or False - update if present
furnaceIsPresent = True     #True or False


savePath = "/root/uSDcard/data/" #location to store data on BBB

maxFileSize = 750000000     #Maximum data filesize before creating a new data file (don't exceed 1GB)


