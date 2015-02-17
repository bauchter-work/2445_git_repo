#!/bin/bash
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

# delay 1 minute to allow for other scripts and processes to execute...
sleep 60 
/usr/bin/nohup /usr/bin/python /srv/field-research/field-code/LoggerMain.py >&/dev/null &
RPORT=$(cat /srv/field-research/field-code/reverseSSHport)

createTunnel() {
  /usr/bin/ssh -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -fN -R $RPORT:localhost:22 2445_CS@app6.ecw.org
  if [[ $? -eq 0 ]]; then
    echo SSH reverse Tunnel response was $?
    echo Reverse Tunnel to app6 created successfully
  else
    echo An error occurred creating a reverse tunnel to app6. RC was $?
  fi
}
echo creating new reverse tunnel connection
createTunnel
echo reverse tunnel open per running process:
/usr/bin/pgrep -f 'ssh .*' -l
echo Device External IP is:
/usr/bin/curl -s curlmyip.com
echo Disk Usage:
/bin/df -h | grep /dev/mmcblk0p2

