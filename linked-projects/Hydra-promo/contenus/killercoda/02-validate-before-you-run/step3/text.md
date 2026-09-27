# Fix the job

Put the correct source id back:

`sed -i 's/src_csv_typo/src_csv/' brokenjob/pipeline.yaml`{{exec}}

`cat brokenjob/pipeline.yaml`{{exec}}

`pipeline.from` now points at `src_csv`, which does exist in `brokenjob/sources.yaml`.

When you are done, click **Check** to continue.
