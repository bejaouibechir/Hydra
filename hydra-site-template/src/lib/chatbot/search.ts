import type { ChatRequest } from './types';
import { EXAMPLES, NOTION_BY_ID, NOTIONS, type CorpusExample } from './knowledge';
import { normalizeText, tokenize } from './normalize';

export interface SearchMatch {
  example: CorpusExample & { searchableDsl: string };
  score: number;
}

function overlapScore(queryTokens: string[], value: string): number {
  const haystack = new Set(tokenize(value));
  return queryTokens.reduce((total, token) => total + (haystack.has(token) ? 1 : 0), 0);
}

export function detectNotion(request: ChatRequest): string | undefined {
  if (request.context.notion && NOTION_BY_ID.has(request.context.notion)) return request.context.notion;
  const selected = normalizeText(request.context.selectedOperation ?? '');
  const query = normalizeText(request.question);
  const queryTokens = new Set(tokenize(query));
  let best: { id: string; score: number } | undefined;
  for (const notion of NOTIONS) {
    let score = 0;
    if (notion.operation && queryTokens.has(notion.operation)) score += 12;
    for (const alias of notion.aliases) {
      const normalizedAlias = normalizeText(alias);
      const matchesAlias = normalizedAlias.includes(' ')
        ? query.includes(normalizedAlias)
        : queryTokens.has(normalizedAlias);
      if (normalizedAlias && matchesAlias) score += normalizedAlias.includes(' ') ? 4 : 2;
    }
    if (!best || score > best.score) best = { id: notion.id, score };
  }
  if (best && best.score > 0) return best.id;
  const contextualTerms = new Set(['current', 'error', 'fail', 'failed', 'failing', 'fix', 'invalid', 'this', 'wrong']);
  const refersToEditorContext = [...queryTokens].some((token) => contextualTerms.has(token));
  return refersToEditorContext ? NOTIONS.find((notion) => notion.operation === selected)?.id : undefined;
}

export function searchExamples(request: ChatRequest, notionId?: string): SearchMatch[] {
  const query = normalizeText(request.question);
  const queryTokens = tokenize(request.question);
  const errorText = request.context.validationErrors?.map((error) => `${error.code ?? ''} ${error.message} ${error.path ?? ''}`).join(' ') ?? '';
  const currentDsl = request.context.currentDsl ?? Object.values(request.context.currentFiles ?? {}).join('\n');

  return EXAMPLES.map((example) => {
    let score = example.notion === notionId ? 16 : 0;
    if (request.context.notion === example.notion) score += 8;
    if (request.context.selectedOperation && example.notion.endsWith(request.context.selectedOperation)) score += 7;
    if (request.context.lessonId && request.context.lessonId === example.id) score += 12;
    if (request.context.validationErrors?.length && example.validation === 'invalid') score += 3;
    score += overlapScore(queryTokens, `${example.id} ${example.title} ${example.question} ${example.answer}`) * 3;
    score += overlapScore(queryTokens, example.searchableDsl) * 1.5;
    score += overlapScore(tokenize(errorText), `${example.expectedErrorContains ?? ''} ${example.answer}`) * 4;
    score += overlapScore(tokenize(currentDsl), example.searchableDsl) * 0.15;
    if (query.includes(normalizeText(example.id))) score += 20;
    return { example, score };
  })
    .filter((match) => match.score > 0)
    .sort((left, right) => right.score - left.score || left.example.id.localeCompare(right.example.id))
    .slice(0, 3);
}

export function confidenceFromScore(score: number): number {
  return Math.max(0, Math.min(1, Number((score / 32).toFixed(2))));
}
