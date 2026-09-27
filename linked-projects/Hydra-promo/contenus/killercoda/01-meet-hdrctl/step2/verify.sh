#!/bin/bash
cd /root/lab || exit 1
test -f myjob/sources.yaml && test -f myjob/destinations.yaml && test -f myjob/pipeline.yaml
