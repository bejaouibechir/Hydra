import { caseA, type CaseStudy } from './migrate-case-a';
import { caseB } from './migrate-case-b';
import { caseC } from './migrate-case-c';

export const caseStudies: Record<string, CaseStudy> = { ...caseA, ...caseB, ...caseC };
