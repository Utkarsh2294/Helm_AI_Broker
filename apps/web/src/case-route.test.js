import { test, expect } from 'vitest';
import { caseIdFromPath } from './case-route';
test('case tools follow both workspaces and reject malformed paths', () => {
  expect(caseIdFromPath('/case/demo-1')).toBe('demo-1');
  expect(caseIdFromPath('/policy-buying/cases/demo-1')).toBe('demo-1');
  expect(caseIdFromPath('/policy-buying')).toBeNull();
  expect(caseIdFromPath('/case/%')).toBeNull();
});
