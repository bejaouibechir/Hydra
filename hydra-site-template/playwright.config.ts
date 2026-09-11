import { defineConfig } from 'playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL: 'http://hydra.local',
    channel: 'msedge',
    headless: true,
  },
});
