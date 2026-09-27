#!/bin/bash
cd /root/lab || exit 1
out=$(hdrctl list 2>/dev/null)
echo "$out" | grep -q "solojob" && ! echo "$out" | grep -q "mypipeline"
