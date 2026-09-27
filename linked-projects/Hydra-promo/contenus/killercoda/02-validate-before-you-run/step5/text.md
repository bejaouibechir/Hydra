# hdrctl run: see the result

It is now safe to run:

`hdrctl run brokenjob`{{exec}}

```
  ✅ Pipeline completed successfully in 0.3s
  Rows read   : 3
  Rows written: 2
```

Three rows read, two written — why? Look at the transformations:

`cat brokenjob/transformations.yaml`{{exec}}

The last step, `filter: value > 0`, drops `Charlie` (value `-5`). Check the result:

`cat brokenjob/data/output.csv`{{exec}}

```
id,name,value
1,Alice,100.0
2,Bob,200.0
```

`pipeline.from`/`to` resolved, the `select`, `cast` and `filter` steps applied, real output written to disk — the execution path `hdrctl validate` never touches, and the reason it is worth checking before you get here.

When you are done, click **Check** to finish.
