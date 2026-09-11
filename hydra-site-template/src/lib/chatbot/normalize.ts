const TOKEN_PATTERN = /[a-z0-9_.$:-]+/gu;

const STOP_WORDS = new Set([
  'a', 'an', 'and', 'are', 'can', 'do', 'does', 'for', 'from', 'how', 'i', 'in',
  'is', 'it', 'my', 'of', 'on', 'or', 'the', 'this', 'to', 'what', 'when',
  'where', 'which', 'why', 'with', 'you', 'your',
]);

export function normalizeText(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/gu, '')
    .toLowerCase()
    .replace(/[’']/gu, '')
    .replace(/[^a-z0-9_.$:\-\s]/gu, ' ')
    .replace(/\s+/gu, ' ')
    .trim();
}

export function tokenize(value: string): string[] {
  const normalized = normalizeText(value);
  return [...new Set(normalized.match(TOKEN_PATTERN) ?? [])].filter(
    (token) => token.length > 1 && !STOP_WORDS.has(token),
  );
}

export function includesPhrase(value: string, phrase: string): boolean {
  return ` ${normalizeText(value)} `.includes(` ${normalizeText(phrase)} `);
}
