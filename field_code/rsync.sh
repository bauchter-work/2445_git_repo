#!/bin/bash
#
# This script reads two files, one containing a local path 
# and one containing a rsync remote path
# on BeagleBone (Black). It rsyncs, then it checks for reverse ssh tunneling
# and if not present then calls for a tunnel again
#
# I only tested this on Debian, but it should probably work on other distros
# as well.
#
# ASSUMES SSH keys have been generated and shared with rsync destination!
echo $(date)
DATAPATH=$(cat /srv/field-research/field-code/localDataPath)
RSYNCPATH=$(cat /srv/field-research/field-code/siteRsyncPath)
/usr/bin/rsync -avz -e ssh $DATAPATH frsa@app6.ecw.org:$RSYNCPATH
#Check for reverse ssh tunnel
RPORT=$(cat /srv/field-research/field-code/reverseSSHport)
createTunnel() {
  /usr/bin/ssh -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -fN -R $RPORT:localhost:22 frsa@app6.ecw.org
  if [[ $? -eq 0 ]]; then
    echo Reverse SSH Response: $?
    echo Reverse Tunnel to app6 created successfully
  else
    echo An error occurred creating a reverse tunnel to app6. RC was $?
  fi
}
/usr/bin/pgrep -f 'ssh .*' -l
echo Process ID of SSH:
/bin/pidof ssh
if [[ $? -ne 0 ]]; then
  echo Creating new reverse tunnel connection on port $RPORT
  createTunnel
else 
  echo Reverse SSH tunnel already open, presumably on port $RPORT
fi
echo Device External IP is:
/usr/bin/curl -s curlmyip.com
echo Disk Usage:
/bin/df -h | grep /dev/mmcblk0p2

