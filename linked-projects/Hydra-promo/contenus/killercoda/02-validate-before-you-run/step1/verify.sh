#!/bin/bash
cd /root/lab || exit 1
grep -q "src_csv_typo" brokenjob/pipeline.yaml
