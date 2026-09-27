# hdrctl workflow list only sees the workflow

`hdrctl workflow list .`{{exec}}

This time `mypipeline` shows up — with its step count — and `solojob` does not. `hdrctl workflow list` searches *recursively* for `workflow.yaml` files, so it would find one nested arbitrarily deep. It just isn't looking for the same thing `hdrctl list` looks for: a job directory versus a workflow manifest.

When you are done, click **Check** to continue.
