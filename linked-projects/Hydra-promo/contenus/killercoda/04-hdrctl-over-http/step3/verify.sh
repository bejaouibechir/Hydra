#!/bin/bash
cd /root/lab || exit 1
curl -s -X POST http://127.0.0.1:5678/api/jobs/validate -H "Content-Type: application/json" -d '{"path": "apijob"}' | grep -q '"success":true'
