#!/bin/bash
echo "Installing Hydra ETL (about 30 seconds)..."
while [ ! -f /tmp/setup-done ]; do sleep 1; done
cd /root/lab
clear
echo "Ready. You are in /root/lab."
