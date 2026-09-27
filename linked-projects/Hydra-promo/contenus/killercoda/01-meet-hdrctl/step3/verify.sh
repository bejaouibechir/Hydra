#!/bin/bash
cd /root/lab || exit 1
test -f mypipeline/workflow.yaml && test -d mypipeline/jobs/job_a && test -d mypipeline/jobs/job_b
