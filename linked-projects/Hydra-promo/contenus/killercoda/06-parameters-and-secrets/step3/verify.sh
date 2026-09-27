#!/bin/bash
F=/root/lab/output/destination_dev.csv
test -f "$F" || exit 1
grep -q "Test Customer A" "$F" || exit 1
test "$(grep -c . "$F")" -eq 4 || exit 1
