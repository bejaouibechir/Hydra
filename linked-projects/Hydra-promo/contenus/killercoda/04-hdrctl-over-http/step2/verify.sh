#!/bin/bash
cd /root/lab || exit 1
curl -s http://127.0.0.1:5678/api/health | grep -q '"status":"ok"'
