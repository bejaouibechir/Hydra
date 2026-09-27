#!/bin/bash
cd /root/lab || exit 1
test -f mypipeline/jobs/job_a/data/output.csv && test -f mypipeline/jobs/job_b/data/output.csv
