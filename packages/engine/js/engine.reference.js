// Helm Broker Portal — reference recommendation engine (plain JavaScript, ESM, zero dependencies)
// Deterministic. The LLM never computes or changes scores; it only narrates them.
// Money in integer pence. All utilities are ABSOLUTE (not cohort-relative) so adding or removing
// a quote can never reorder the other quotes (no rank reversal).

export const CRITERIA = [
  'affordability', 'coverage', 'network', 'underwriting',
  'insurer_quality', 'process_ease', 'terms_clarity',
];

const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const sum = (a) => a.reduce((s, x) => s + x, 0);
const sigmoid = (x) => 1 / (1 + Math.exp(-x));

// ---------- 1. Weights ----------
// Rank-Order Centroid: w_i = (1/m) * sum_{k=i..m} 1/k   (i is 1-indexed)
export function rocWeights(m) {
  return Array.from({ length: m }, (_, i) =>
    sum(Array.from({ length: m - i }, (_, k) => 1 / (i + 1 + k))) / m);
}

// priorityOrder: criteria names, most important first (may be partial). Unranked share 15% equally.
export function userWeights(priorityOrder, criteria = CRITERIA) {
  const ranked = priorityOrder.filter((c) => criteria.includes(c));
  const rest = criteria.filter((c) => !ranked.includes(c));
  const massRanked = rest.length ? 0.85 : 1;
  const roc = rocWeights(ranked.length || 1);
  const w = {};
  ranked.forEach((c, i) => { w[c] = massRanked * roc[i]; });
  rest.forEach((c) => { w[c] = 0.15 / rest.length; });
  return w;
}

// Blend user weights with learned weights; learning is capped (lambda<=0.25, +/-30% per criterion).
export function combineWeights(wUser, wLearned, { lambda = 0.25, cap = 0.3, floor = 0.02 } = {}) {
  const lam = Math.min(lambda, 0.25);
  const lo = {}, hi = {}, blended = {};
  for (const c of CRITERIA) {
    const base = wUser[c];
    blended[c] = (1 - lam) * base + lam * (wLearned?.[c] ?? base);
    lo[c] = Math.max(floor, base * (1 - cap));
    hi[c] = Math.max(lo[c], base * (1 + cap));
  }
  // Find shift s with sum(clamp(blended + s, lo, hi)) = 1. The sum is monotone in s, so bisect.
  // This keeps the +/-cap guarantee AFTER normalisation (clamp-then-renormalise would break it).
  const total = (s) => sum(CRITERIA.map((c) => clamp(blended[c] + s, lo[c], hi[c])));
  let a = -1, b = 1;
  for (let i = 0; i < 80; i++) { const m = (a + b) / 2; if (total(m) < 1) a = m; else b = m; }
  const s = (a + b) / 2;
  const out = Object.fromEntries(CRITERIA.map((c) => [c, clamp(blended[c] + s, lo[c], hi[c])]));
  const t = sum(Object.values(out));
  if (Math.abs(t - 1) > 1e-9) for (const c of CRITERIA) out[c] /= t;   // only if bounds were infeasible
  return out;
}

// ---------- 2. Hard gates (non-compensatory) ----------
export function gate(plan, ctx) {
  const reasons = [];
  let needsHuman = false;
  if (plan.status && plan.status !== 'quoted') reasons.push(`insurer_${plan.status}`);
  if (ctx.hardBudgetCapPence && plan.annualPremiumPence > ctx.hardBudgetCapPence) reasons.push('over_hard_budget_cap');
  for (const [k, spec] of Object.entries(ctx.desiredCoverage || {})) {
    if (spec.mustHave && (plan.coverage?.[k] ?? 0) < spec.level) reasons.push(`must_have_missing:${k}`);
  }
  if (ctx.allowedUnderwriting && !ctx.allowedUnderwriting.includes(plan.underwritingType)) reasons.push('underwriting_not_allowed');
  // arithmetic check: premium must equal base + IPT within 1 penny per 100 pounds
  if (plan.basePremiumPence != null) {
    const expected = Math.round(plan.basePremiumPence * (1 + (ctx.iptRate ?? 0.12)));
    if (Math.abs(expected - plan.annualPremiumPence) > Math.max(2, plan.annualPremiumPence / 10000)) {
      needsHuman = true; reasons.push('premium_arithmetic_mismatch');
    }
  }
  if (plan.medicalFlagsAmbiguous) { needsHuman = true; reasons.push('ambiguous_medical_terms_route_to_human'); }
  return { pass: reasons.filter((r) => r !== 'premium_arithmetic_mismatch' && r !== 'ambiguous_medical_terms_route_to_human').length === 0 && !needsHuman,
    needsHuman, reasons };
}

// ---------- 3. Criterion utilities in [0,1] ----------
export function utilities(plan, ctx) {
  const freq = ctx.claimFreq ?? 0.25;
  const expClaim = ctx.expectedClaimPence ?? 300000;
  const teco = plan.annualPremiumPence + freq * Math.min(plan.excessPence ?? 0, expClaim);
  const budget = ctx.budgetAnnualPence ?? ctx.bench.p90 * 0.9;
  const uBudget = 1 / (1 + Math.exp(6 * (teco / budget - 1)));
  const uRef = clamp((ctx.bench.p90 - teco) / (ctx.bench.p90 - ctx.bench.p10));
  const affordability = 0.5 * uBudget + 0.5 * uRef;

  const dc = Object.values(ctx.desiredCoverage || {});
  const impSum = sum(dc.map((d) => d.importance)) || 1;
  const coverage = sum(Object.entries(ctx.desiredCoverage || {}).map(([k, d]) =>
    d.importance * clamp((plan.coverage?.[k] ?? 0) / Math.max(d.level, 1)))) / impSum;

  const network = 0.6 * clamp(plan.hospitalListLevel / Math.max(ctx.desiredHospitalLevel ?? 1, 1))
    + 0.4 * clamp(plan.preferredHospitalShare ?? 0);

  const burden = clamp(sum(plan.exclusionSeverities ?? []) / (ctx.maxSeverity ?? 10));
  const typeMatch = plan.underwritingType === ctx.preferredUnderwriting ? 1 : 0.5;
  const underwriting = 0.7 * (1 - burden) + 0.3 * typeMatch;

  const st = plan.insurerStats ?? {};
  const n0 = 30, p0 = ctx.priorUpheldRate ?? 0.25;               // Bayesian shrinkage for sparse complaint data
  const shrunkUphold = ((st.n ?? 0) * (st.upheldRate ?? p0) + n0 * p0) / ((st.n ?? 0) + n0);
  const insurer_quality = 0.5 * (1 - shrunkUphold) + 0.3 * clamp(st.finStrength ?? 0.5) + 0.2 * clamp(st.slaScore ?? 0.5);

  const process_ease = clamp(1 - 0.6 * ((plan.docsUnavailable ?? 0) / Math.max(plan.docsRequired ?? 1, 1))
    - 0.4 * Math.min((plan.turnaroundDays ?? 7) / 14, 1));

  const terms_clarity = clamp(0.5 * (plan.ipidCompleteness ?? 0.5) + 0.3 * (plan.plainLanguage ?? 0.5)
    + 0.2 * (1 - Math.min((plan.exclusionsCount ?? 10) / 20, 1)));

  return { affordability, coverage, network, underwriting, insurer_quality, process_ease, terms_clarity, _teco: teco };
}

// ---------- 4. Aggregation: additive fit + fixed-reference TOPSIS balance ----------
export function aggregate(u, w) {
  const wsm = sum(CRITERIA.map((c) => w[c] * u[c]));                                    // 0..1
  const dPlus = Math.sqrt(sum(CRITERIA.map((c) => w[c] * (1 - u[c]) ** 2)));            // distance to ideal (all 1)
  const dMinus = Math.sqrt(sum(CRITERIA.map((c) => w[c] * u[c] ** 2)));                 // distance to anti-ideal (all 0)
  const topsis = dMinus / (dPlus + dMinus || 1);                                        // 0..1, fixed reference points
  const score = 100 * (0.7 * wsm + 0.3 * topsis);
  const points = Object.fromEntries(CRITERIA.map((c) => [c, +(100 * w[c] * u[c]).toFixed(2)])); // sums to 100*wsm
  return { score, fit: 100 * wsm, balance: 100 * topsis, points };
}

export function rankPlans(plans, ctx, weights) {
  const rows = [];
  const excluded = [];
  for (const p of plans) {
    const g = gate(p, ctx);
    if (!g.pass) { excluded.push({ id: p.id, reasons: g.reasons, needsHuman: g.needsHuman }); continue; }
    const u = utilities(p, ctx);
    rows.push({ id: p.id, insurerId: p.insurerId, u, ...aggregate(u, weights) });
  }
  rows.sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
  return { rows, excluded };
}

// Diversity: at most `maxPerInsurer` in the shortlist
export function diversify(rows, k = 5, maxPerInsurer = 2) {
  const out = []; const count = {};
  for (const r of rows) {
    if ((count[r.insurerId] ?? 0) >= maxPerInsurer) continue;
    out.push(r); count[r.insurerId] = (count[r.insurerId] ?? 0) + 1;
    if (out.length === k) break;
  }
  return out;
}

// ---------- 5. Uncertainty: Monte-Carlo over weights (Dirichlet) ----------
function mulberry32(a) { return () => { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function randn(rng) { let u = 0, v = 0; while (u === 0) u = rng(); v = rng(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
function gammaSample(shape, rng) { // Marsaglia–Tsang
  if (shape < 1) return gammaSample(shape + 1, rng) * Math.pow(rng(), 1 / shape);
  const d = shape - 1 / 3, c = 1 / Math.sqrt(9 * d);
  for (;;) { let x, v; do { x = randn(rng); v = 1 + c * x; } while (v <= 0); v = v ** 3; const u = rng();
    if (u < 1 - 0.0331 * x ** 4 || Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v; }
}
export function mcStability(rows, weights, { draws = 1000, kappa = 60, seed = 7 } = {}) {
  const rng = mulberry32(seed); const n = rows.length;
  const stat = Object.fromEntries(rows.map((r) => [r.id, { top1: 0, top5: 0, rankSum: 0, scores: [] }]));
  for (let t = 0; t < draws; t++) {
    const g = CRITERIA.map((c) => gammaSample(kappa * weights[c], rng)); const s = sum(g);
    const w = Object.fromEntries(CRITERIA.map((c, i) => [c, g[i] / s]));
    const sc = rows.map((r) => ({ id: r.id, s: aggregate(r.u, w).score })).sort((a, b) => b.s - a.s);
    sc.forEach((x, i) => { const st = stat[x.id]; if (i === 0) st.top1++; if (i < 5) st.top5++; st.rankSum += i + 1; st.scores.push(x.s); });
  }
  return Object.fromEntries(rows.map((r) => { const st = stat[r.id]; st.scores.sort((a, b) => a - b);
    return [r.id, { pTop1: st.top1 / draws, pTop5: st.top5 / draws, meanRank: st.rankSum / draws,
      ci95: [st.scores[Math.floor(0.025 * draws)], st.scores[Math.floor(0.975 * draws)]] }]; }));
}

// ---------- 6. Counterfactual: smallest weight shift that flips a vs b ----------
export function flipAnalysis(a, b, weights, { step = 0.01, maxShift = 0.3 } = {}) {
  const base = aggregate(a.u, weights).score - aggregate(b.u, weights).score;
  let best = null;
  for (const from of CRITERIA) for (const to of CRITERIA) {
    if (from === to) continue;
    for (let d = step; d <= Math.min(maxShift, weights[from] - 0.02) + 1e-9; d += step) {
      const w = { ...weights, [from]: weights[from] - d, [to]: weights[to] + d };
      const diff = aggregate(a.u, w).score - aggregate(b.u, w).score;
      if (Math.sign(diff) !== Math.sign(base)) { if (!best || d < best.shift) best = { from, to, shift: +d.toFixed(2) }; break; }
    }
  }
  return { margin: +base.toFixed(2), flip: best };
}

// ---------- 7. Learning (Agent 5): Bradley–Terry on broker choices, MAP with prior on current weights ----------
// comparisons: [{ better: utilityVector, worse: utilityVector, weight?: number }]
export function learnWeights(baseW, comparisons, { beta = 8, lr = 0.5, epochs = 300, reg = 1.0 } = {}) {
  const theta0 = CRITERIA.map((c) => Math.log(baseW[c]));
  let theta = theta0.slice();
  const softmax = (t) => { const m = Math.max(...t); const e = t.map((x) => Math.exp(x - m)); const s = sum(e); return e.map((x) => x / s); };
  for (let ep = 0; ep < epochs; ep++) {
    const w = softmax(theta); const grad = new Array(CRITERIA.length).fill(0);
    for (const cmp of comparisons) {
      const ub = CRITERIA.map((c) => cmp.better[c]), uw = CRITERIA.map((c) => cmp.worse[c]);
      const sb = sum(w.map((x, i) => x * ub[i])), sw = sum(w.map((x, i) => x * uw[i]));
      const p = sigmoid(beta * (sb - sw)); const k = (cmp.weight ?? 1) * beta * (1 - p);
      for (let i = 0; i < grad.length; i++) grad[i] += k * (w[i] * (ub[i] - sb) - w[i] * (uw[i] - sw));
    }
    const n = Math.max(comparisons.length, 1);
    for (let i = 0; i < theta.length; i++) theta[i] += lr * (grad[i] / n - reg * 0.1 * (theta[i] - theta0[i]));   // MAP: pull back toward current weights
  }
  const w = softmax(theta);
  return Object.fromEntries(CRITERIA.map((c, i) => [c, w[i]]));
}

// Shrink learned weights toward base by evidence: n/(n+n0)
export function shrinkLearned(baseW, learnedW, n, n0 = 50) {
  const a = n / (n + n0);
  return Object.fromEntries(CRITERIA.map((c) => [c, (1 - a) * baseW[c] + a * learnedW[c]]));
}

// Offline evaluation metric: NDCG@k of engine ranking vs broker's chosen set (binary relevance)
export function ndcgAtK(rankedIds, chosenIds, k = 3) {
  const dcg = rankedIds.slice(0, k).reduce((s, id, i) => s + (chosenIds.includes(id) ? 1 : 0) / Math.log2(i + 2), 0);
  const ideal = Array.from({ length: Math.min(k, chosenIds.length) }, (_, i) => 1 / Math.log2(i + 2)).reduce((s, x) => s + x, 0);
  return ideal ? dcg / ideal : 0;
}
