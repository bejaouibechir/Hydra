import { normalizeText } from './normalize';

export interface DirectAnswer {
  id: string;
  notion: string;
  all: string[];
  any?: string[];
  answer: string;
  guideHref: string;
}

const ANSWERS: readonly DirectAnswer[] = [
  { id: 'what-is-hydra', notion: 'dsl.job_pipeline', all: ['what', 'hydra'], any: ['is hydra', 'hydra etl'], answer: 'Hydra is an ETL platform for defining data sources, transformations, destinations, pipelines, and multi-job workflows with a YAML-based DSL. The same job definition can be used through Hydra’s CLI, API, or Studio.', guideHref: '/guide/' },
  { id: 'job-vs-workflow', notion: 'dsl.job_pipeline', all: ['job', 'workflow'], any: ['difference', 'different', 'compare'], answer: 'A job defines one ETL execution: source, ordered transformations, and destination. A workflow orchestrates several jobs, their dependencies, scheduling, and retry behavior.', guideHref: '/guide/workflows/' },
  { id: 'minimal-job-files', notion: 'dsl.job_pipeline', all: ['job', 'files'], any: ['minimal', 'required', 'need', 'necessary'], answer: 'A minimal Hydra job needs sources.yaml, destinations.yaml, and pipeline.yaml. Add transformations.yaml only when the job performs transformations.', guideHref: '/guide/jobs/' },
  { id: 'pipeline-references', notion: 'dsl.job_pipeline', all: ['pipeline'], any: ['reference', 'references', 'source', 'destination'], answer: 'pipeline.from references a source ID declared in sources.yaml, and pipeline.to references a destination ID declared in destinations.yaml. The IDs must match exactly.', guideHref: '/guide/jobs/' },
  { id: 'optional-transformations', notion: 'dsl.job_pipeline', all: ['transformations'], any: ['required', 'optional', 'every pipeline'], answer: 'No. transformations.yaml is optional. A pipeline can copy data directly from a source to a destination without transformation steps.', guideHref: '/guide/jobs/' },
  { id: 'csv-source', notion: 'dsl.source', all: ['csv', 'source'], any: ['declare', 'define', 'minimal'], answer: 'Declare an ID under sources, set type: csv, and put the file path in extract.table. connection can remain empty for a local file.', guideHref: '/guide/sources/' },
  { id: 'query-vs-table', notion: 'dsl.source', all: ['extract.query', 'extract.table'], any: ['instead', 'difference', 'when'], answer: 'Use extract.table to read a table or file target directly. Use extract.query when the database must execute an explicit SQL selection before Hydra extracts the rows.', guideHref: '/guide/sources/' },
  { id: 'mongodb-collection', notion: 'dsl.source', all: ['mongodb', 'collection'], answer: 'For MongoDB, set the connector type to mongodb and place the collection name in extract.collection. Connection credentials should come from environment variables.', guideHref: '/guide/sources/' },
  { id: 'replace-mode', notion: 'dsl.destination', all: ['replace'], any: ['load.mode', 'mode', 'does'], answer: 'load.mode: replace recreates or overwrites the destination result on each run. Use it when the output must be reproducible rather than appended to existing data.', guideHref: '/guide/destinations/' },
  { id: 'upsert-key', notion: 'dsl.destination', all: ['upsert', 'key'], any: ['require', 'requires', 'why'], answer: 'An upsert needs load.key so Hydra can identify an existing row. Matching keys are updated; keys not found in the destination are inserted.', guideHref: '/guide/destinations/' },
  { id: 'upsert-duplicates', notion: 'dsl.destination', all: ['upsert'], any: ['duplicate', 'duplicated', 'prevent'], answer: 'Upsert compares each incoming row using load.key. If the key already exists, Hydra updates that row instead of inserting a duplicate.', guideHref: '/guide/destinations/' },
  { id: 'select-operation', notion: 'transform.select', all: ['select'], any: ['work', 'columns', 'keep', 'remove'], answer: 'select keeps only the columns listed in columns. Their order in the list also becomes their order in the output.', guideHref: '/guide/transformations/select/' },
  { id: 'filter-combine', notion: 'transform.filter', all: ['filter'], any: ['combine', 'conditions', 'paid', 'orders'], answer: 'Use filter.expr with exact input column names. Combine conditions with and, for example: amount >= 100 and status == "paid".', guideHref: '/guide/transformations/filter/' },
  { id: 'calculate-total', notion: 'transform.calculate', all: ['calculate'], any: ['price', 'quantity', 'total'], answer: 'Use calculate with total as the target column and price * quantity as the expression. Hydra evaluates it for every input row.', guideHref: '/guide/transformations/calculate/' },
  { id: 'cast-multiple', notion: 'transform.cast', all: ['cast'], any: ['multiple', 'several', 'one step'], answer: 'Yes. One cast step can convert several columns by adding each column and target type to cast.mapping.', guideHref: '/guide/transformations/cast/' },
  { id: 'cast-float', notion: 'transform.cast', all: ['amount'], any: ['float', 'convert', 'calculation'], answer: 'Use cast.mapping to map amount to float. After conversion, amount can be used safely in numeric calculations.', guideHref: '/guide/transformations/cast/' },
  { id: 'aggregate-customer', notion: 'transform.aggregate', all: ['customer'], any: ['aggregate', 'total amount', 'per customer'], answer: 'Use aggregate with group_by: [customer_id], then define total_amount with sum on amount. Add a count output if you also need the number of orders.', guideHref: '/guide/transformations/aggregate/' },
  { id: 'join-different-keys', notion: 'transform.join', all: ['join', 'keys'], any: ['different', 'names', 'left_key', 'right_key'], answer: 'When key names differ, set left_key to the current stream column and right_key to the matching column in the joined source.', guideHref: '/guide/transformations/join/' },
  { id: 'join-customer-id', notion: 'transform.join', all: ['join', 'customer_id'], answer: 'Reference the source to join, use customer_id as the common key, and choose the required join type such as inner or left.', guideHref: '/guide/transformations/join/' },
  { id: 'workflow-order', notion: 'dsl.workflow', all: ['workflow'], any: ['order', 'wait', 'depends_on', 'dependency'], answer: 'Use depends_on between workflow steps. A step runs only after every step listed in its depends_on field has completed successfully.', guideHref: '/guide/workflows/' },
  { id: 'workflow-retry', notion: 'dsl.workflow', all: ['workflow'], any: ['retry', 'retries', 'failure', 'temporary'], answer: 'Add a retry policy to the workflow step for transient failures. For scheduled execution, also configure the schedule trigger with a cron expression.', guideHref: '/guide/workflows/' },
  { id: 'workflow-schedule', notion: 'dsl.workflow', all: ['schedule'], any: ['cron', 'daily', 'every day', '8'], answer: 'A schedule trigger requires trigger.cron. For every day at 08:00, use cron: "0 8 * * *".', guideHref: '/guide/workflows/' },
] as const;

export function findDirectAnswer(question: string): DirectAnswer | undefined {
  const normalized = normalizeText(question);
  return ANSWERS.find((entry) => {
    const hasAll = entry.all.every((term) => normalized.includes(normalizeText(term)));
    const hasAny = !entry.any || entry.any.some((term) => normalized.includes(normalizeText(term)));
    return hasAll && hasAny;
  });
}
