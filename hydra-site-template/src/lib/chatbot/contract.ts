import {
  CHATBOT_CONTRACT_VERSION,
  type AssistanceLevel,
  type ChatRequest,
  type ChatResponse,
  type ScopeDecision,
} from './types';

export const CHATBOT_LIMITS = Object.freeze({
  maxQuestionCharacters: 500,
  maxAnswerWords: 140,
  maxCitations: 3,
  maxSuggestedActions: 3,
  minimumConfidence: 0,
  maximumConfidence: 1,
});

export const SUPPORTED_NOTIONS = Object.freeze([
  'dsl.job_pipeline',
  'dsl.source',
  'dsl.destination',
  'transform.select',
  'transform.filter',
  'transform.calculate',
  'transform.cast',
  'transform.aggregate',
  'transform.join',
  'dsl.workflow',
] as const);

const ASSISTANCE_LEVELS: ReadonlySet<AssistanceLevel> = new Set([
  'hint_1',
  'hint_2',
  'explanation',
  'solution',
]);

const SCOPE_DECISIONS: ReadonlySet<ScopeDecision> = new Set([
  'answer',
  'answer_with_limitation',
  'answer_unknown_feature',
  'decline',
  'decline_and_redirect',
  'decline_external_action',
  'secret_warning',
  'refuse_instruction_override',
  'no_match',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function isChatRequest(value: unknown): value is ChatRequest {
  if (!isRecord(value) || !isRecord(value.context)) return false;
  return (
    value.contractVersion === CHATBOT_CONTRACT_VERSION &&
    typeof value.requestId === 'string' &&
    value.requestId.length > 0 &&
    value.locale === 'en' &&
    typeof value.question === 'string' &&
    value.question.trim().length > 0 &&
    value.question.length <= CHATBOT_LIMITS.maxQuestionCharacters &&
    ASSISTANCE_LEVELS.has(value.assistanceLevel as AssistanceLevel) &&
    value.context.hydraVersion === '1.2.0' &&
    value.context.dslVersion === '1.1' &&
    (value.context.executionMode === 'local_simulation' ||
      value.context.executionMode === 'static_example')
  );
}

export function isChatResponse(value: unknown): value is ChatResponse {
  if (!isRecord(value)) return false;
  if (!Array.isArray(value.citations)) return false;
  if (!Array.isArray(value.matchedExampleIds)) return false;
  if (!Array.isArray(value.actions)) return false;
  const confidence = value.confidence;
  const wordCount =
    typeof value.answer === 'string' ? value.answer.trim().split(/\s+/u).filter(Boolean).length : 0;
  return (
    value.contractVersion === CHATBOT_CONTRACT_VERSION &&
    typeof value.requestId === 'string' &&
    value.requestId.length > 0 &&
    typeof value.answer === 'string' &&
    value.answer.trim().length > 0 &&
    wordCount <= CHATBOT_LIMITS.maxAnswerWords &&
    ASSISTANCE_LEVELS.has(value.assistanceLevel as AssistanceLevel) &&
    SCOPE_DECISIONS.has(value.scopeDecision as ScopeDecision) &&
    typeof confidence === 'number' &&
    confidence >= CHATBOT_LIMITS.minimumConfidence &&
    confidence <= CHATBOT_LIMITS.maximumConfidence &&
    value.citations.length <= CHATBOT_LIMITS.maxCitations &&
    value.actions.length <= CHATBOT_LIMITS.maxSuggestedActions
  );
}

