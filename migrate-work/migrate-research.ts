import { researchA, type ResearchSection } from './migrate-research-a';
import { researchB } from './migrate-research-b';
import { researchC } from './migrate-research-c';
import { researchD } from './migrate-research-d';
import { researchE } from './migrate-research-e';
import { researchF } from './migrate-research-f';
import { researchG } from './migrate-research-g';
import { researchH } from './migrate-research-h';
import { researchI } from './migrate-research-i';

export const researchPages: Record<string, ResearchSection[]> = {
  ...researchA, ...researchB, ...researchC, ...researchD, ...researchE,
  ...researchF, ...researchG, ...researchH, ...researchI,
};
