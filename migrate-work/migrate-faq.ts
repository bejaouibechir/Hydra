import { faqA, type FaqExpansion } from './migrate-faq-a';
import { faqB } from './migrate-faq-b';
import { faqC } from './migrate-faq-c';
import { faqD } from './migrate-faq-d';
import { faqE } from './migrate-faq-e';
import { faqF } from './migrate-faq-f';
import { faqG } from './migrate-faq-g';
import { faqH } from './migrate-faq-h';
import { faqI } from './migrate-faq-i';

export const faqExpansions: Record<string, FaqExpansion[]> = {
  ...faqA,
  ...faqB,
  ...faqC,
  ...faqD,
  ...faqE,
  ...faqF,
  ...faqG,
  ...faqH,
  ...faqI,
};
