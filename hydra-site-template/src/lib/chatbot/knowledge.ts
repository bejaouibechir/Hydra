import corpus from '../../data/hydra-dsl/examples.json';

export type ExampleVariant = 'minimal' | 'practical' | 'challenge' | 'correction';

export interface CorpusExample {
  id: string;
  notion: string;
  variant: ExampleVariant;
  title: string;
  question: string;
  answer: string;
  hints: string[];
  validation: 'valid' | 'invalid';
  expectedErrorContains?: string;
  kind: string;
  yaml?: string;
  files?: Record<string, string>;
}

export interface NotionKnowledge {
  id: string;
  label: string;
  operation?: string;
  aliases: string[];
  summary: string;
  firstHint: string;
  secondHint: string;
  guideHref: string;
}

export const NOTIONS: readonly NotionKnowledge[] = [
  { id: 'dsl.job_pipeline', label: 'job and pipeline', aliases: ['job', 'pipeline', 'pipeline.yaml', 'from', 'to', 'transformations.yaml'], summary: 'A minimal job connects a declared source ID to a declared destination ID through pipeline.from and pipeline.to. transformations.yaml is optional.', firstHint: 'Compare pipeline.from and pipeline.to with the IDs declared under sources and destinations.', secondHint: 'Those references must match the declared IDs exactly; connector types such as csv are not IDs.', guideHref: '/guide/jobs/' },
  { id: 'dsl.source', label: 'source', aliases: ['source', 'sources.yaml', 'extract', 'table', 'query', 'collection', 'batch_size', 'csv', 'postgresql', 'mongodb'], summary: 'A source has an ID, a connector type, and an extract target: table, query, or collection. Put credentials in environment variables.', firstHint: 'Inspect the source type and the properties nested under extract.', secondHint: 'extract needs a target such as table, query, or collection; batch_size alone is not a target.', guideHref: '/guide/sources/' },
  { id: 'dsl.destination', label: 'destination', aliases: ['destination', 'destinations.yaml', 'load', 'replace', 'append', 'upsert', 'key'], summary: 'A destination declares a connector and load settings. replace recreates output; upsert also needs a stable load.key.', firstHint: 'Check load.mode and the target under load.table.', secondHint: 'If mode is upsert, add a stable key list such as key: [order_id].', guideHref: '/guide/destinations/' },
  { id: 'transform.select', label: 'select', operation: 'select', aliases: ['select', 'columns', 'column', 'reorder', 'remove columns', 'keep columns'], summary: 'select keeps only the columns listed in columns, in the same order as that list.', firstHint: 'List only the columns you want to keep.', secondHint: 'Every listed name must exist in the input schema, and list order controls output order.', guideHref: '/guide/transformations/select/' },
  { id: 'transform.filter', label: 'filter', operation: 'filter', aliases: ['filter', 'where', 'expr', 'condition', 'and', 'pending', 'paid'], summary: 'filter keeps rows for which expr evaluates to true. Column names in the expression must exist in the input.', firstHint: 'Write the condition against exact input column names.', secondHint: 'Combine conditions with and, for example amount >= 100 and status == "paid".', guideHref: '/guide/transformations/filter/' },
  { id: 'transform.calculate', label: 'calculate', operation: 'calculate', aliases: ['calculate', 'calculation', 'formula', 'expression', 'new column', 'price', 'quantity', 'tax', 'total'], summary: 'calculate creates or replaces a target column by evaluating an expression over input columns.', firstHint: 'Identify the target column and the input columns used by the expression.', secondHint: 'Use exact input names, for example total: price * quantity.', guideHref: '/guide/transformations/calculate/' },
  { id: 'transform.cast', label: 'cast', operation: 'cast', aliases: ['cast', 'convert', 'conversion', 'mapping', 'type', 'float', 'integer', 'string', 'boolean', 'decimal'], summary: 'cast converts one or more columns with mapping. For this Hydra version, use supported types such as float rather than decimal.', firstHint: 'Map each input column to a supported Hydra cast type.', secondHint: 'Multiple column/type pairs can be placed in the same mapping.', guideHref: '/guide/transformations/cast/' },
  { id: 'transform.aggregate', label: 'aggregate', operation: 'aggregate', aliases: ['aggregate', 'aggregation', 'group', 'group_by', 'agg', 'avg', 'sum', 'count', 'customer_id'], summary: 'aggregate groups rows with group_by and defines named outputs in agg using functions such as sum, count, or avg.', firstHint: 'Choose existing grouping columns before defining aggregate outputs.', secondHint: 'Each output in agg needs an input column and an aggregation function.', guideHref: '/guide/transformations/aggregate/' },
  { id: 'transform.join', label: 'join', operation: 'join', aliases: ['join', 'merge', 'inner', 'left', 'right', 'left_key', 'right_key', 'customer_id'], summary: 'join combines the current stream with a declared source. Use key when names match, or left_key and right_key when they differ.', firstHint: 'Verify the right source and the key present in each input.', secondHint: 'Use left_key and right_key when the two key names are different.', guideHref: '/guide/transformations/join/' },
  { id: 'dsl.workflow', label: 'workflow', aliases: ['workflow', 'step', 'depends_on', 'schedule', 'cron', 'retry', 'retries', 'trigger'], summary: 'A workflow orders jobs with depends_on. A schedule trigger requires cron, and transient failures can use a retry policy.', firstHint: 'Check step dependencies and the selected trigger type.', secondHint: 'For a schedule, provide trigger.cron; use depends_on to enforce execution order.', guideHref: '/guide/workflows/' },
] as const;

export const EXAMPLES = (corpus.examples as CorpusExample[]).map((example) => ({
  ...example,
  searchableDsl: [example.yaml, ...Object.values(example.files ?? {})].filter(Boolean).join('\n'),
}));

export const NOTION_BY_ID = new Map(NOTIONS.map((notion) => [notion.id, notion]));

export const KNOWN_OPERATIONS = new Set([
  'aggregate', 'calculate', 'cast', 'clean', 'deduplicate', 'fill_null', 'filter',
  'join', 'merge', 'pivot', 'rename', 'script', 'select', 'sort', 'transpose',
  'trim', 'union', 'unpivot',
]);
