#!/bin/bash
cd /root/lab || exit 1
sleep 1
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5678/api/health | grep -q "200"
