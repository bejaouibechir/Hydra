# Catch the typo before 2 a.m.

A tired edit at 6 p.m. Simulate it by misspelling `bash` in the first step:

`sed -i '0,/action: bash/s//action: bsah/' workflow.yaml && grep -n "bsah" workflow.yaml`{{exec}}

In a crontab, a typo is found at 2 a.m., by the job not running. Here, check the file first:

`hdrctl workflow validate workflow.yaml; echo "exit code: $?"`{{exec}}

The workflow is **refused**: the error names the step, lists the valid actions and suggests `bash`. `hdrctl workflow run` refuses to start the same way, so a misspelled step can never report success by doing nothing.

Put `hdrctl workflow validate` in the pull request check of the repository that holds this file, and the typo never reaches the server.

Fix it:

`sed -i 's/action: bsah/action: bash/' workflow.yaml && hdrctl workflow validate workflow.yaml`{{exec}}
