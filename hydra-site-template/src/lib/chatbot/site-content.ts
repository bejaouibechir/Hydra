import { normalizeText, tokenize } from './normalize';

export interface SiteContentResult {
  id: string;
  title: string;
  description: string;
  href: string;
  score: number;
}

interface SiteContentDocument extends Omit<SiteContentResult, 'score'> {
  keywords: string[];
}

const DOCUMENTS: readonly SiteContentDocument[] = [
  { id: 'hydra-home', title: 'Hydra ETL overview', description: 'Discover Hydra, its DSL, CLI, API, Studio, and core data-platform concepts.', href: '/', keywords: ['hydra', 'etl', 'overview', 'platform', 'introduction', 'getting started'] },
  { id: 'hydra-guide', title: 'Hydra Guide', description: 'Install Hydra, connect data systems, define jobs, and run pipelines.', href: '/guide', keywords: ['guide', 'install', 'installation', 'connect', 'run', 'cli', 'api', 'studio'] },
  { id: 'dsl-overview', title: 'Hydra DSL transformations', description: 'Browse filtering, sorting, deduplication, aggregation, and table reshaping operations.', href: '/dsl', keywords: ['dsl', 'transformation', 'filter', 'sort', 'deduplicate', 'aggregate', 'reshape', 'operation'] },
  { id: 'first-job', title: 'Tutorial: your first Hydra job', description: 'Build a first job with a source, transformations, destination, and pipeline manifest.', href: '/dsl/tutorial/01-first-job', keywords: ['tutorial', 'first job', 'beginner', 'source', 'destination', 'pipeline', 'yaml', 'manifest'] },
  { id: 'dsl-sources', title: 'DSL sources and connections', description: 'Configure source connectors, connection properties, extraction targets, and credentials.', href: '/dsl/sources', keywords: ['source', 'sources', 'connection', 'connector', 'csv', 'json', 'postgresql', 'mysql', 'mongodb', 'extract', 'credentials'] },
  { id: 'dsl-pipeline', title: 'DSL pipeline block', description: 'Connect one declared source to one destination and reference transformation steps.', href: '/dsl/pipeline', keywords: ['pipeline', 'from', 'to', 'job', 'source', 'destination', 'transformations'] },
  { id: 'dsl-interpolation', title: 'DSL interpolation and environment variables', description: 'Use environment variables and interpolation safely in Hydra YAML manifests.', href: '/dsl/interpolation', keywords: ['interpolation', 'environment', 'variable', 'env', 'secret', 'credential', 'placeholder'] },
  { id: 'dsl-reference', title: 'Complete Hydra DSL reference', description: 'Explore connector types, operation blocks, manifest structure, and supported capabilities.', href: '/dsl/reference', keywords: ['reference', 'schema', 'syntax', 'connector', 'operation', 'manifest', 'capability'] },
  { id: 'build', title: 'Build with Hydra', description: 'Learn how Hydra jobs connect to CLI, API, Studio, and project workflows.', href: '/build', keywords: ['build', 'project', 'cli', 'api', 'studio', 'integration'] },
  { id: 'migrate', title: 'Migration guide', description: 'Compare Hydra with Airflow, Dagster, Prefect, dbt, Databricks, and Airbyte.', href: '/migrate', keywords: ['migrate', 'migration', 'compare', 'airflow', 'dagster', 'prefect', 'dbt', 'databricks', 'airbyte'] },
  { id: 'migrate-airflow', title: 'Migrate from Airflow', description: 'Translate Airflow DAG concepts and tasks into Hydra jobs and workflows.', href: '/migrate/airflow', keywords: ['airflow', 'dag', 'task', 'operator', 'migration'] },
  { id: 'migrate-dagster', title: 'Migrate from Dagster', description: 'Translate Dagster assets and jobs into Hydra manifests.', href: '/migrate/dagster', keywords: ['dagster', 'asset', 'job', 'migration'] },
  { id: 'migrate-prefect', title: 'Migrate from Prefect', description: 'Translate Prefect flows and tasks into Hydra workflows.', href: '/migrate/prefect', keywords: ['prefect', 'flow', 'task', 'migration'] },
  { id: 'migrate-dbt', title: 'Use dbt with Hydra', description: 'Add the extraction and loading layers surrounding dbt transformations.', href: '/migrate/dbt', keywords: ['dbt', 'model', 'loading', 'extraction', 'migration'] },
  { id: 'migrate-databricks', title: 'Migrate from Databricks', description: 'Translate Databricks notebooks and bundles into portable Hydra jobs.', href: '/migrate/databricks', keywords: ['databricks', 'notebook', 'bundle', 'cluster', 'migration'] },
  { id: 'migrate-airbyte', title: 'Migrate from Airbyte', description: 'Translate Airbyte connections and streams into Hydra manifests.', href: '/migrate/airbyte', keywords: ['airbyte', 'connection', 'stream', 'sync', 'migration'] },
] as const;

const SYNONYMS: Readonly<Record<string, readonly string[]>> = {
  docs: ['guide', 'reference', 'tutorial'],
  documentation: ['guide', 'reference', 'tutorial'],
  password: ['secret', 'credential', 'environment'],
  secrets: ['secret', 'credential', 'environment', 'interpolation'],
  schedule: ['workflow', 'cron'],
  scheduling: ['workflow', 'cron'],
  start: ['beginner', 'tutorial', 'first job'],
};

function expandedTokens(question: string): string[] {
  const base = tokenize(question);
  return [...new Set(base.flatMap((token) => [token, ...(SYNONYMS[token] ?? [])].flatMap(tokenize)))];
}

export function searchSiteContent(question: string, limit = 3): SiteContentResult[] {
  const normalizedQuestion = normalizeText(question);
  const tokens = expandedTokens(question);
  return DOCUMENTS.map((document) => {
    const title = normalizeText(document.title);
    const description = normalizeText(document.description);
    const keywords = document.keywords.map(normalizeText);
    const titleTokens = new Set(tokenize(title));
    const descriptionTokens = new Set(tokenize(description));
    const keywordTokens = new Set(keywords.flatMap(tokenize));
    let score = 0;
    for (const token of tokens) {
      if (titleTokens.has(token)) score += 5;
      if (keywordTokens.has(token)) score += 4;
      if (descriptionTokens.has(token)) score += 2;
    }
    if (keywords.some((keyword) => normalizedQuestion.includes(keyword) && keyword.includes(' '))) score += 6;
    return { id: document.id, title: document.title, description: document.description, href: document.href, score };
  })
    .filter((result) => result.score >= 4)
    .sort((left, right) => right.score - left.score || left.title.localeCompare(right.title))
    .slice(0, limit);
}
