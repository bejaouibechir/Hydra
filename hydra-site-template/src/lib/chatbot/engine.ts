import { CHATBOT_LIMITS, isChatRequest, isChatResponse } from './contract';
import { findDirectAnswer } from './direct-answers';
import { KNOWN_OPERATIONS, NOTION_BY_ID } from './knowledge';
import { normalizeText, tokenize } from './normalize';
import { applyPriorityPolicy } from './policies';
import { confidenceFromScore, detectNotion, searchExamples } from './search';
import { searchSiteContent } from './site-content';
import {
  CHATBOT_CONTRACT_VERSION,
  type ChatCitation,
  type ChatRequest,
  type ChatResponse,
  type SuggestedAction,
} from './types';

const UNSUPPORTED_FEATURES: Record<string, string> = {
  derive: 'Hydra DSL 1.1 uses calculate, not derive.',
  index: 'index is not a registered Hydra DSL 1.1 transformation.',
  slack: 'A Slack connector is listed in catalogue material but has no runtime handler in the current implementation.',
  web_api: 'web_api is not registered as a runtime connector in the covered version.',
};

function words(value: string): number {
  return value.trim().split(/\s+/u).filter(Boolean).length;
}

function trimToLimit(value: string): string {
  if (words(value) <= CHATBOT_LIMITS.maxAnswerWords) return value;
  return `${value.trim().split(/\s+/u).slice(0, CHATBOT_LIMITS.maxAnswerWords - 1).join(' ')}…`;
}

function baseResponse(request: ChatRequest, partial: Omit<ChatResponse, 'contractVersion' | 'requestId' | 'assistanceLevel'>): ChatResponse {
  const response: ChatResponse = {
    contractVersion: CHATBOT_CONTRACT_VERSION,
    requestId: request.requestId,
    assistanceLevel: request.assistanceLevel,
    ...partial,
    answer: trimToLimit(partial.answer),
    citations: partial.citations.slice(0, CHATBOT_LIMITS.maxCitations),
    actions: partial.actions.slice(0, CHATBOT_LIMITS.maxSuggestedActions),
  };
  if (!isChatResponse(response)) throw new Error('The deterministic engine produced an invalid ChatResponse.');
  return response;
}

function policyResponse(request: ChatRequest): ChatResponse | undefined {
  const policy = applyPriorityPolicy(request);
  if (!policy) return undefined;
  return baseResponse(request, {
    ...policy,
    citations: [],
    matchedExampleIds: [],
    actions: [{ id: 'open-guide', type: 'open_guide', label: 'Open the Hydra DSL guide', href: '/guide/' }],
    executionNotice: 'No remote model or external service was called.',
  });
}

function limitationResponse(request: ChatRequest): ChatResponse | undefined {
  const normalized = normalizeText(request.question);
  for (const [feature, message] of Object.entries(UNSUPPORTED_FEATURES)) {
    if (tokenize(normalized).includes(feature)) {
      return baseResponse(request, {
        answer: `${message} I can help you use a supported Hydra DSL construct instead.`,
        citations: [{ id: `compat-${feature}`, label: 'Hydra DSL 1.1 compatibility', kind: 'compatibility', href: '/guide/compatibility/', sourcePath: 'documentations/chatbot-hydra-dsl/01-inventaire-officiel-dsl.md' }],
        scopeDecision: 'answer_with_limitation',
        confidence: 1,
        matchedExampleIds: [],
        actions: [{ id: 'open-migrate', type: 'open_migrate', label: 'Open compatibility guide', href: '/migrate/' }],
      });
    }
  }

  const operationMatch = normalized.match(/(?:operation|transformation)\s+([a-z_][a-z0-9_]*)/u);
  const contextualFailureWords = new Set(['error', 'fail', 'failed', 'fails', 'invalid', 'work', 'working', 'works']);
  if (
    operationMatch &&
    !contextualFailureWords.has(operationMatch[1]) &&
    !KNOWN_OPERATIONS.has(operationMatch[1])
  ) {
    return baseResponse(request, {
      answer: `I cannot verify “${operationMatch[1]}” as a Hydra DSL 1.1 transformation. Check the supported operations or ask about the intended result.`,
      citations: [{ id: 'schema-index', label: 'Supported DSL schemas', kind: 'schema', href: '/guide/transformations/', sourcePath: 'documentations/chatbot-hydra-dsl/schemas/index.json' }],
      scopeDecision: 'answer_unknown_feature',
      confidence: 0.96,
      matchedExampleIds: [],
      actions: [{ id: 'open-transformations', type: 'open_guide', label: 'View supported transformations', href: '/guide/transformations/' }],
    });
  }
  return undefined;
}

function directAnswerResponse(request: ChatRequest): ChatResponse | undefined {
  const direct = findDirectAnswer(request.question);
  if (!direct || request.assistanceLevel === 'hint_1' || request.assistanceLevel === 'hint_2') return undefined;
  const matches = searchExamples(request, direct.notion);
  const citations: ChatCitation[] = [];
  if (matches[0]) {
    citations.push({
      id: `example-${matches[0].example.id}`,
      label: matches[0].example.title,
      kind: 'example',
      href: `/learn/?example=${encodeURIComponent(matches[0].example.id)}`,
      sourcePath: 'documentations/chatbot-hydra-dsl/examples/examples.json',
    });
  }
  citations.push({ id: `guide-${direct.id}`, label: 'Hydra DSL guide', kind: 'guide', href: direct.guideHref, sourcePath: `hydra-site-template${direct.guideHref}` });
  return baseResponse(request, {
    answer: direct.answer,
    citations,
    scopeDecision: 'answer',
    confidence: 0.99,
    matchedExampleIds: matches.map((match) => match.example.id),
    actions: [
      { id: 'open-guide', type: 'open_guide', label: 'Open the relevant guide', href: direct.guideHref },
      { id: 'open-playground', type: 'open_playground', label: 'Try it in Playground', href: '/playground/' },
    ],
    executionNotice: 'Answer generated locally from the bundled Hydra DSL corpus; no LLM or network request was used.',
  });
}

function answerForLevel(request: ChatRequest, notionId: string, exampleId?: string): string {
  const notion = NOTION_BY_ID.get(notionId)!;
  switch (request.assistanceLevel) {
    case 'hint_1': return notion.firstHint;
    case 'hint_2': return notion.secondHint;
    case 'explanation': return notion.summary;
    case 'solution': return `${notion.summary}${exampleId ? ' Load the matched example to inspect the complete valid YAML.' : ''}`;
  }
}

function actionsFor(request: ChatRequest, guideHref: string, exampleId?: string): SuggestedAction[] {
  if (request.assistanceLevel === 'hint_1') return [{ id: 'next-hint', type: 'show_next_hint', label: 'Show another hint' }];
  if (request.assistanceLevel === 'hint_2') return [{ id: 'show-solution', type: 'show_solution', label: 'Show the solution' }];
  const actions: SuggestedAction[] = [{ id: 'open-guide', type: 'open_guide', label: 'Open the relevant guide', href: guideHref }];
  if (exampleId) actions.unshift({ id: 'load-example', type: 'load_example', label: 'Load matched example', exampleId });
  actions.push({ id: 'open-playground', type: 'open_playground', label: 'Try it in Playground', href: '/playground/' });
  return actions;
}

function siteContentFallback(request: ChatRequest): ChatResponse {
  const results = searchSiteContent(request.question);
  if (results.length) {
    return baseResponse(request, {
      answer: 'I could not find a validated direct answer, but these site resources may help. They are suggestions based on the terms in your question.',
      citations: results.map((result) => ({ id: `site-${result.id}`, label: result.title, kind: 'guide' as const, href: result.href, sourcePath: `hydra-site${result.href}` })),
      scopeDecision: 'answer_with_limitation',
      confidence: Math.min(0.79, Number((0.45 + results[0].score / 100).toFixed(2))),
      matchedExampleIds: [],
      actions: results.map((result) => ({ id: `open-${result.id}`, type: 'open_guide' as const, label: result.title, href: result.href })),
      executionNotice: 'Resources selected locally from the bundled site-content index; no LLM or network request was used.',
    });
  }
  return baseResponse(request, {
    answer: 'I could not identify a matching Hydra topic or site resource. Please specify whether your question is about jobs and pipelines, sources, transformations, destinations, workflows, or migration.',
    citations: [],
    scopeDecision: 'no_match',
    confidence: 0,
    matchedExampleIds: [],
    actions: [
      { id: 'browse-dsl', type: 'open_guide', label: 'Browse Hydra DSL', href: '/dsl' },
      { id: 'browse-guide', type: 'open_guide', label: 'Open the Guide', href: '/guide' },
      { id: 'browse-migrate', type: 'open_migrate', label: 'Explore migration guides', href: '/migrate' },
    ],
  });
}

export function answerHydraDsl(request: ChatRequest): ChatResponse {
  if (!isChatRequest(request)) throw new TypeError('Invalid ChatRequest.');
  const priority = policyResponse(request);
  if (priority) return priority;
  const limitation = limitationResponse(request);
  if (limitation) return limitation;
  const direct = directAnswerResponse(request);
  if (direct) return direct;

  const notionId = detectNotion(request);
  if (!notionId) {
    return siteContentFallback(request);
  }

  const matches = searchExamples(request, notionId);
  const best = matches[0];
  const notion = NOTION_BY_ID.get(notionId)!;
  const exampleIds = matches.map((match) => match.example.id);
  const citations: ChatCitation[] = best ? [{
    id: `example-${best.example.id}`,
    label: best.example.title,
    kind: 'example',
    href: `/learn/?example=${encodeURIComponent(best.example.id)}`,
    sourcePath: 'documentations/chatbot-hydra-dsl/examples/examples.json',
  }] : [];
  citations.push({ id: `guide-${notionId}`, label: `${notion.label} guide`, kind: 'guide', href: notion.guideHref, sourcePath: `hydra-site-template${notion.guideHref}` });

  return baseResponse(request, {
    answer: answerForLevel(request, notionId, best?.example.id),
    citations,
    scopeDecision: 'answer',
    confidence: best ? confidenceFromScore(best.score) : 0.55,
    matchedExampleIds: exampleIds,
    actions: actionsFor(request, notion.guideHref, best?.example.id),
    executionNotice: 'Answer generated locally from the bundled Hydra DSL corpus; no LLM or network request was used.',
  });
}
