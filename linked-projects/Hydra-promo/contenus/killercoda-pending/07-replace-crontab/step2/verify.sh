#!/bin/bash
cd /root/nightly
hdrctl workflow validate workflow.yaml >/dev/null 2>&1 &&
grep -q "depends_on" workflow.yaml &&
grep -q "5 orders" reports/report.txt
