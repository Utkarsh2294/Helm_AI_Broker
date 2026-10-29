import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', workers: 1, retries: 0, timeout: 60000,
  expect: { timeout: 15000 },
  use: { baseURL: process.env.HELM_QA_URL || 'http://127.0.0.1:5182', channel: 'msedge', headless: true, screenshot: 'only-on-failure' },
  reporter: [['list']],
});
