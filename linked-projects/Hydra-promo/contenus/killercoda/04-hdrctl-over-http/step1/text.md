# Scaffold a job and start hdrctl serve

`hdrctl init apijob --template csv`{{exec}}

Start the API in the background, without Studio (`--no-studio` — no UI to serve, just the REST surface):

`hdrctl serve --no-studio --port 5678 > /tmp/serve.log 2>&1 &`{{exec}}

`sleep 2 && cat /tmp/serve.log`{{exec}}

You should see `Studio disabled — started with --no-studio` and the API address. It keeps running in the background for the rest of this lab.

When you are done, click **Check** to continue.
