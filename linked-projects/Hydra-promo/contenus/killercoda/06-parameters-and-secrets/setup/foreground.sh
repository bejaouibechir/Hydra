#!/bin/bash
echo "Starting two MySQL databases and installing Hydra ETL..."
echo "(this takes about a minute — the intro is worth reading meanwhile)"
while [ ! -f /tmp/setup-done ]; do sleep 1; done
cd /root/lab
clear
if [ -f /tmp/setup-warning ]; then cat /tmp/setup-warning; echo; fi
echo "Ready. You are in /root/lab."
