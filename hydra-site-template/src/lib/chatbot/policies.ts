import type { ChatRequest, ScopeDecision } from './types';
import { normalizeText } from './normalize';

export interface PolicyResult {
  scopeDecision: ScopeDecision;
  answer: string;
  confidence: number;
}

const SECRET_PATTERNS = [
  /-----begin (?:rsa |ec |openssh )?private key-----/iu,
  /(?:api[_ -]?key|access[_ -]?token|password|secret)\s*[:=]\s*\S{6,}/iu,
  /\b(?:sk-[a-z0-9_-]{16,}|ghp_[a-z0-9]{20,}|akia[0-9a-z]{16})\b/iu,
];

const OVERRIDE_PATTERN = /(?:ignore|disregard|forget).{0,35}(?:instructions|rules|prompt)|(?:system|developer)\s+prompt|jailbreak/iu;
const EXTERNAL_ACTION_PATTERN = /\b(?:deploy|publish|push|commit|delete|email|send|upload)\b.{0,30}\b(?:for me|now|this)\b/iu;
const OUT_OF_SCOPE_PATTERN = /\b(?:weather|medical|lawyer|stock price|recipe|football|politics)\b/iu;

export function applyPriorityPolicy(request: ChatRequest): PolicyResult | undefined {
  const question = request.question;
  if (request.context.containsPotentialSecret || SECRET_PATTERNS.some((pattern) => pattern.test(question))) {
    return {
      scopeDecision: 'secret_warning',
      answer: 'This may contain a credential or private key. Remove it before continuing, rotate it if it was real, and reference secrets through environment variables such as ${ENV:PG_PASSWORD}.',
      confidence: 1,
    };
  }
  if (OVERRIDE_PATTERN.test(question)) {
    return {
      scopeDecision: 'refuse_instruction_override',
      answer: 'I cannot override my Hydra DSL scope or hidden rules. I can still help you understand, diagnose, or correct Hydra DSL.',
      confidence: 1,
    };
  }
  if (EXTERNAL_ACTION_PATTERN.test(question)) {
    return {
      scopeDecision: 'decline_external_action',
      answer: 'This static assistant cannot change files, deploy, publish, or contact external services. I can explain the Hydra DSL change and provide a safe example for you to apply.',
      confidence: 0.98,
    };
  }
  if (OUT_OF_SCOPE_PATTERN.test(normalizeText(question))) {
    return {
      scopeDecision: 'decline_and_redirect',
      answer: 'That is outside Hydra DSL learning. Ask me about jobs, sources, destinations, transformations, or workflows instead.',
      confidence: 0.98,
    };
  }
  return undefined;
}
