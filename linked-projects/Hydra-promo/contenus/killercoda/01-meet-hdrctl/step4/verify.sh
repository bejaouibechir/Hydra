#!/bin/bash
cd /root/lab || exit 1
hdrctl list 2>/dev/null | grep -q myjob
