#!/bin/sh
#
# This script reads two files, one containing a local path 
# and one containing a rsync remote path
# on BeagleBone (Black). 
#
# I only tested this on Debian, but it should probably work on other distros
# as well.
#
# ASSUMES SSH keys have been generated and shared with rsync destination!

DATAPATH=$(cat localDataPath)
RSYNCPATH=$(cat rsyncPath)
rsync -avz -e ssh $DATAPATH frsa@app6.ecw.org:$RSYNCPATH
