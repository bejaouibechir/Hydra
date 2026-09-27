#!/bin/bash
cd /root/nightly
grep -q "retry:" workflow.yaml &&
hdrctl workflow validate workflow.yaml >/dev/null 2>&1 &&
test -f /tmp/flaky.done
