import { answerHydraDsl } from '../../../hydra-site-template/src/lib/chatbot/engine';
import { EXAMPLES } from '../../../hydra-site-template/src/lib/chatbot/knowledge';

declare global {
  interface Window {
    hydraChat: {
      answerHydraDsl: typeof answerHydraDsl;
      examples: typeof EXAMPLES;
    };
  }
}

window.hydraChat = { answerHydraDsl, examples: EXAMPLES };
