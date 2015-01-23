#!/bin/sh
#
# This script runs at boot-up if the service is enabled 
# First it launches the Logger program.
#
# After that, it tries to read one file which specifies the reverse tunnel port
# for this remote field device.  
# ASSUMES FILE EXISTS.  
# ASSUMES FILE HAS A VALID PORT THAT HASN'T BEEN ALLOCATED ALREADY
# 
# ASSUMES SSH keys have been generated and shared with rsync destination!
/usr/bin/nohup /usr/bin/python /srv/field-research/field-code/LoggerMain.py >&/dev/null &
RPORT=$(cat /srv/field-research/field-code/reverseSSHport)
/usr/bin/ssh -fN -R $RPORT:localhost:22 frsa@app6.ecw.org >&/dev/null &