#!/bin/bash
cd /root/lab || exit 1
grep -q "mode: upsert$" dbjob/destinations.yaml
