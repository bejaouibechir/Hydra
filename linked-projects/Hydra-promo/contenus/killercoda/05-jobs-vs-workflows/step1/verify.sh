#!/bin/bash
cd /root/lab || exit 1
test -f solojob/pipeline.yaml && test -f mypipeline/workflow.yaml && test -f mypipeline/jobs/job_a/pipeline.yaml && test -f mypipeline/jobs/job_b/pipeline.yaml
