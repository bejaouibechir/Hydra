/** Contrat public du moteur de réponse Hydra DSL. */

export const CHATBOT_CONTRACT_VERSION = '1.0' as const;

export type AssistanceLevel = 'hint_1' | 'hint_2' | 'explanation' | 'solution';

export type ScopeDecision =
  | 'answer'
  | 'answer_with_limitation'
  | 'answer_unknown_feature'
  | 'decline'
  | 'decline_and_redirect'
  | 'decline_external_action'
  | 'secret_warning'
  | 'refuse_instruction_override'
  | 'no_match';

export type CitationKind = 'schema' | 'example' | 'guide' | 'compatibility';

export type SuggestedActionType =
  | 'show_next_hint'
  | 'show_solution'
  | 'load_example'
  | 'open_guide'
  | 'open_playground'
  | 'open_migrate';

export interface ValidationErrorContext {
  code?: string;
  message: string;
  path?: string;
  value?: unknown;
}

export interface ChatContext {
  /** Version produit affichée à l'utilisateur. */
  hydraVersion: '1.2.0';
  /** Version du corpus et des parseurs couverts. */
  dslVersion: '1.1';
  /** Identifiant stable, par exemple transform.filter. */
  notion?: string;
  lessonId?: string;
  lessonStep?: string;
  selectedOperation?: string;
  selectedProperty?: string;
  currentDsl?: string;
  currentFiles?: Record<string, string>;
  inputRows?: Array<Record<string, unknown>>;
  rightRows?: Array<Record<string, unknown>>;
  outputRows?: Array<Record<string, unknown>>;
  validationErrors?: ValidationErrorContext[];
  executionMode: 'local_simulation' | 'static_example';
  containsPotentialSecret?: boolean;
}

export interface ChatRequest {
  contractVersion: typeof CHATBOT_CONTRACT_VERSION;
  requestId: string;
  /** Le site public est en anglais pour le MVP. */
  locale: 'en';
  question: string;
  assistanceLevel: AssistanceLevel;
  context: ChatContext;
}

export interface ChatCitation {
  id: string;
  label: string;
  kind: CitationKind;
  /** Chemin relatif compatible avec la base GitHub Pages. */
  href: string;
  sourcePath: string;
}

export interface SuggestedAction {
  id: string;
  type: SuggestedActionType;
  label: string;
  href?: string;
  exampleId?: string;
}

export interface ChatResponse {
  contractVersion: typeof CHATBOT_CONTRACT_VERSION;
  requestId: string;
  answer: string;
  citations: ChatCitation[];
  assistanceLevel: AssistanceLevel;
  scopeDecision: ScopeDecision;
  /** Score déterministe de correspondance, entre 0 et 1. */
  confidence: number;
  matchedExampleIds: string[];
  actions: SuggestedAction[];
  /** Rappelle qu'aucun moteur distant n'a été exécuté, si pertinent. */
  executionNotice?: string;
}

export interface ChatbotContractError {
  code:
    | 'EMPTY_QUESTION'
    | 'QUESTION_TOO_LONG'
    | 'INVALID_CONTEXT'
    | 'INVALID_RESPONSE';
  message: string;
}

