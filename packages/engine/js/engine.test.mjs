import test from 'node:test';
import assert from 'node:assert/strict';
import * as E from './engine.reference.js';

const ctx = {
  budgetAnnualPence: 90000, bench: { p10: 50000, p90: 160000 }, iptRate: 0.12,
  desiredCoverage: { cancer: { level: 3, importance: 1, mustHave: true }, mental: { level: 2, importance: 0.6 }, outpatient: { level: 3, importance: 0.8 } },
  desiredHospitalLevel: 2, preferredUnderwriting: 'moratorium', maxSeverity: 10,
};
const mk = (id, insurerId, base, over = {}) => ({
  id, insurerId, status: 'quoted', basePremiumPence: base, annualPremiumPence: Math.round(base * 1.12), excessPence: 25000,
  coverage: { cancer: 3, mental: 2, outpatient: 3 }, hospitalListLevel: 2, preferredHospitalShare: 0.7,
  exclusionSeverities: [], underwritingType: 'moratorium',
  insurerStats: { n: 200, upheldRate: 0.2, finStrength: 0.8, slaScore: 0.7 },
  docsRequired: 4, docsUnavailable: 0, turnaroundDays: 3, ipidCompleteness: 0.9, plainLanguage: 0.8, exclusionsCount: 8, commissionPct: 15, ...over,
});
const plans = [
  mk('A1', 'A', 70000), mk('A2', 'A', 85000, { coverage: { cancer: 3, mental: 3, outpatient: 3 }, hospitalListLevel: 3 }),
  mk('A3', 'A', 60000, { coverage: { cancer: 2, mental: 1, outpatient: 1 } }),
  mk('B1', 'B', 78000, { underwritingType: 'fmu', exclusionSeverities: [3, 2] }),
  mk('C1', 'C', 95000, { hospitalListLevel: 3, preferredHospitalShare: 0.95, insurerStats: { n: 40, upheldRate: 0.1, finStrength: 0.9, slaScore: 0.9 } }),
  mk('D1', 'D', 66000, { docsRequired: 5, docsUnavailable: 3, turnaroundDays: 12, ipidCompleteness: 0.5 }),
  mk('E1', 'E', 72000, { annualPremiumPence: 99999 }),     // arithmetic mismatch -> human
];
const wUser = E.userWeights(['affordability', 'coverage', 'network']);

test('ROC weights m=3 are the textbook values and sum to 1', () => {
  const w = E.rocWeights(3);
  assert.ok(Math.abs(w[0] - 0.6111) < 1e-3 && Math.abs(w[1] - 0.2778) < 1e-3 && Math.abs(w[2] - 0.1111) < 1e-3);
  assert.ok(Math.abs(E.sum?.(w) ?? w.reduce((a, b) => a + b, 0) - 1) < 1e-9);
});
test('user weights sum to 1', () => assert.ok(Math.abs(Object.values(wUser).reduce((a, b) => a + b, 0) - 1) < 1e-9));
test('combined weights sum to 1 and the +/-30% cap and floor hold AFTER normalisation', () => {
  const learned = Object.fromEntries(E.CRITERIA.map((c) => [c, c === 'network' ? 0.9 : 0.1 / 6]));
  const w = E.combineWeights(wUser, learned);
  assert.ok(Math.abs(Object.values(w).reduce((a, b) => a + b, 0) - 1) < 1e-9);
  for (const c of E.CRITERIA) {
    const lo = Math.max(0.02, wUser[c] * 0.7), hi = Math.max(lo, wUser[c] * 1.3);
    assert.ok(w[c] >= lo - 1e-9 && w[c] <= hi + 1e-9, `${c}: ${wUser[c]} -> ${w[c]} outside [${lo}, ${hi}]`);
  }
  assert.ok(w.network > wUser.network, `network ${wUser.network} -> ${w.network}`);
});
test('combineWeights with learned == user leaves weights unchanged', () => {
  const w = E.combineWeights(wUser, wUser);
  for (const c of E.CRITERIA) assert.ok(Math.abs(w[c] - wUser[c]) < 1e-9 || wUser[c] < 0.02);
});
test('gates: missing must-have excluded; arithmetic mismatch routed to human; not scored', () => {
  const r = E.rankPlans([...plans, mk('X', 'X', 70000, { coverage: { cancer: 1, mental: 2, outpatient: 3 } })], ctx, wUser);
  assert.ok(r.excluded.find((e) => e.id === 'X').reasons.includes('must_have_missing:cancer'));
  const e = r.excluded.find((x) => x.id === 'E1'); assert.ok(e && e.needsHuman);
  assert.ok(!r.rows.find((x) => x.id === 'E1'));
});
test('scores within 0..100 and points sum equals fit', () => {
  const { rows } = E.rankPlans(plans, ctx, wUser);
  for (const r of rows) {
    assert.ok(r.score >= 0 && r.score <= 100);
    const pts = Object.values(r.points).reduce((a, b) => a + b, 0);
    assert.ok(Math.abs(pts - r.fit) < 0.05, `${pts} vs ${r.fit}`);
  }
});
test('monotonic: cheaper premium never lowers the score', () => {
  const a = E.rankPlans([mk('P', 'A', 80000)], ctx, wUser).rows[0].score;
  const b = E.rankPlans([mk('P', 'A', 70000)], ctx, wUser).rows[0].score;
  assert.ok(b > a);
});
test('no rank reversal: removing any other plan never changes a plan\'s score or the relative order of the rest', () => {
  const full = E.rankPlans(plans, ctx, wUser).rows; const ids = full.map((r) => r.id);
  for (const drop of ids) {
    const sub = E.rankPlans(plans.filter((p) => p.id !== drop), ctx, wUser).rows;
    assert.deepEqual(sub.map((r) => r.id), ids.filter((i) => i !== drop));
    for (const r of sub) assert.equal(r.score, full.find((x) => x.id === r.id).score);
  }
});
test('commission-blind: changing commission does not change any score', () => {
  const a = E.rankPlans(plans, ctx, wUser).rows.map((r) => r.score);
  const b = E.rankPlans(plans.map((p) => ({ ...p, commissionPct: 40 })), ctx, wUser).rows.map((r) => r.score);
  assert.deepEqual(a, b);
});
test('deterministic: same inputs -> identical outputs', () => {
  assert.deepEqual(E.rankPlans(plans, ctx, wUser), E.rankPlans(plans, ctx, wUser));
});
test('Monte-Carlo stability: seeded, probabilities consistent', () => {
  const { rows } = E.rankPlans(plans, ctx, wUser);
  const a = E.mcStability(rows, wUser, { seed: 1 }), b = E.mcStability(rows, wUser, { seed: 1 });
  assert.deepEqual(a, b);
  const top1 = Object.values(a).reduce((s, x) => s + x.pTop1, 0);
  assert.ok(Math.abs(top1 - 1) < 1e-9);
  assert.ok(a[rows[0].id].pTop1 >= a[rows[rows.length - 1].id].pTop1);
});
test('diversity: at most 2 per insurer in the shortlist', () => {
  const { rows } = E.rankPlans(plans, ctx, wUser);
  const s = E.diversify(rows, 5, 2); const cnt = {};
  s.forEach((r) => { cnt[r.insurerId] = (cnt[r.insurerId] || 0) + 1; });
  assert.ok(Object.values(cnt).every((c) => c <= 2)); assert.equal(s.length, 5);
});
test('flip analysis returns a minimal weight shift when top-2 are close', () => {
  const { rows } = E.rankPlans(plans, ctx, wUser);
  const f = E.flipAnalysis(rows[0], rows[1], wUser);
  assert.ok(f.margin >= 0); if (f.flip) assert.ok(f.flip.shift > 0 && f.flip.shift <= 0.3);
});
test('learning: broker consistently preferring network moves network weight up; shrinkage + cap bound the effect', () => {
  const { rows } = E.rankPlans(plans, ctx, wUser);
  const comps = [];
  for (let i = 0; i < 60; i++) {
    const hi = rows.reduce((m, r) => (r.u.network > m.u.network ? r : m), rows[0]);
    const lo = rows.reduce((m, r) => (r.u.network < m.u.network ? r : m), rows[0]);
    comps.push({ better: hi.u, worse: lo.u });
  }
  const learned = E.learnWeights(wUser, comps);
  assert.ok(learned.network > wUser.network, `${wUser.network} -> ${learned.network}`);
  assert.ok(Math.abs(Object.values(learned).reduce((a, b) => a + b, 0) - 1) < 1e-9);
  const shr = E.shrinkLearned(wUser, learned, 10); // little evidence -> stays near base
  assert.ok(Math.abs(shr.network - wUser.network) < Math.abs(learned.network - wUser.network));
  const final = E.combineWeights(wUser, shr);
  assert.ok(final.network <= wUser.network * 1.3 + 0.02);
});
test('NDCG@3 sanity', () => {
  assert.equal(E.ndcgAtK(['a', 'b', 'c', 'd'], ['a', 'b', 'c']), 1);
  assert.ok(E.ndcgAtK(['d', 'a', 'b', 'c'], ['a', 'b', 'c']) < 1);
});
test('worked example prints (informational)', () => {
  const { rows, excluded } = E.rankPlans(plans, ctx, wUser);
  const st = E.mcStability(rows, wUser, { seed: 42 });
  console.log('\nWEIGHTS', Object.fromEntries(Object.entries(wUser).map(([k, v]) => [k, +v.toFixed(3)])));
  console.table(rows.map((r) => ({ id: r.id, score: +r.score.toFixed(1), fit: +r.fit.toFixed(1), balance: +r.balance.toFixed(1),
    aff: +r.u.affordability.toFixed(2), cov: +r.u.coverage.toFixed(2), net: +r.u.network.toFixed(2), uw: +r.u.underwriting.toFixed(2),
    qual: +r.u.insurer_quality.toFixed(2), ease: +r.u.process_ease.toFixed(2), clar: +r.u.terms_clarity.toFixed(2),
    pTop1: st[r.id].pTop1, pTop5: st[r.id].pTop5 })));
  console.log('EXCLUDED', JSON.stringify(excluded));
  console.log('FLIP #1 vs #2', JSON.stringify(E.flipAnalysis(rows[0], rows[1], wUser)));
});
