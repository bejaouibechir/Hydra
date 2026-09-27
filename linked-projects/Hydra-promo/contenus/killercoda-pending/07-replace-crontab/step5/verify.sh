#!/bin/bash
crontab -l 2>/dev/null | grep -q "hdrctl workflow run"
