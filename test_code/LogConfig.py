#! /usr/bin/python

# Configuration Information for BeagleBone Black datalogging

siteName = "bbbMPLS"        #Give your site a unique Name (this will be embedded in the output files)
                            #Don't use spaces or special characters.  Underscores are fine.

useFTP = False              #Set to True or False
ftpURL = "secure.ecw.org"   #FTP address to open connection to
ftpUser = "abc_123"         #Username for FTP authentication
ftpPassword = "abc_123"     #Password for FTP authentication
ftpPath = "2458/rPiDev"     #Directory to CD to at the FTP address
ftpUploadInterval = 5       #Time interval to refresh the remote data file (in minutes)

pollRate = 0.0              #Time delay between sequential device requests in units of seconds   
timeoutValue = .5           #Time to wait for a device response in units of seconds
sleepTime = 5               #Time delay between polling rounds in units of seconds

maxFileSize = 750000000     #Maximum data filesize before creating a new data file (don't exceed 1GB)
maxRetries = 2              #Maximum times to retry querying for a each data packet

#Password for gateway login, captured in SHA1 hashtag form
# Enter new hashtag if you change the password - just google SHA1 encoding
passwordSHA1 = "5343a78157a12a7a8a135364599378e762f2b121"

coordinatorAddress = '1633'  #not used in dbus code
messengerAddress = '55e8'    #not used in dbus code

harmonyEth1Ip = "192.168.3.103"  #not used in dbus code
harmonyEth1Port = 50333          #not used in dbus code
