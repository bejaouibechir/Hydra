#!/bin/bash
cd /root/nightly
! grep -q "bsah" workflow.yaml &&
hdrctl workflow validate workflow.yaml >/dev/null 2>&1
