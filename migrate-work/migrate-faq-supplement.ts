export const faqSupplement: Record<string, Record<number, string>> = {
  airflow: {
    10: 'For each DAG, identify who owns the schedule, historical intervals, alert routing and final published relation; these responsibilities determine whether a complete replacement is realistic.',
    19: 'Include queued tasks and paused schedules in the recovery checklist, because a successful data restore can still be undone by an unexpected late task.',
  },
  kestra: {
    5: 'When a flow includes a human approval, external event or infrastructure task, keep that boundary visible in the architecture. Replacing its data-processing segment does not automatically replace the surrounding operational process.',
    6: 'Write the maximum combined attempt count in the runbook.',
    11: 'Record explicit exceptions for retained plugins.',
    12: 'Include any output URI passed between steps.',
    18: 'Check that the container image includes the same Hydra plugins used in development and that its mounted project is readable by the runtime user.',
  },
  flowman: {
    3: 'Also compare whether a mapping materializes an intermediate dataset or merely defines a lazy relation. That distinction changes when an error appears and how much work a retry repeats.',
    6: 'Document downstream schema consumers before changing field names.',
    10: 'Keep a versioned output manifest.',
    12: 'Where one Flowman relation acts as both an intermediate input and a final sink, split those roles in the Hydra design and document which process owns each persisted copy.',
    13: 'Compare row ordering only when consumers depend on it.',
    14: 'Include database write pressure in resource measurements.',
    15: 'A manifest should state expected partitions and row counts so Hydra can reject an incomplete Spark output before publishing anything downstream.',
    17: 'Keep the selected input partition frozen throughout the comparison.',
    19: 'Verify restored consumer routing.',
  },
  dagster: {
    2: 'For a partitioned asset, preserve the relationship between the specific Hydra run and its Dagster materialization event. Include the source partition, target version and validation status so backfills and incident reviews remain traceable after the compute implementation changes.',
    6: 'If a check is advisory rather than blocking, preserve that distinction. Operators need to see both the materialization and the failed check; otherwise a green job can conceal a quality regression that Dagster previously highlighted.',
    10: 'Save the actual target version in asset metadata, not just the intended table name, so a failed or retried run can be distinguished from the published one.',
    11: 'Keep asset owners involved in the decision.',
    12: 'Record multi-output publication order.',
    15: 'Export historical metadata before retiring an asset wrapper.',
    18: 'Add one partition backfill to the trial before cutover.',
  },
};
