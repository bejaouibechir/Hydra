#!/bin/bash
cd /root/lab || exit 1
grep -q "from: src_csv$" brokenjob/pipeline.yaml
