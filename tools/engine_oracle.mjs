// Independent scalar arithmetic oracle; input and output are JSON on stdio.
let text = ''; for await (const chunk of process.stdin) text += chunk;
const clamp = x => Math.max(0, Math.min(1, x));
const output = JSON.parse(text).map(({ plan: p, needs: n, weights: w }) => {
  const cost = p.annualPremiumPence + 0.25 * Math.min(p.excessPence, 300000);
  const importance = Object.values(n.coverage).reduce((a, v) => a + v.importance, 0);
  const s = p.insurerStats;
  const u = {
    affordability: 0.5 / (1 + Math.exp(6 * (cost / n.budget_annual_pence - 1))) + 0.5 * clamp((n.reference_high_pence - cost) / (n.reference_high_pence - n.reference_low_pence)),
    coverage: importance ? Object.entries(n.coverage).reduce((a, [k, v]) => a + v.importance * clamp((p.coverage[k] || 0) / Math.max(1, v.level)), 0) / importance : 0.5,
    network: 0.6 * clamp(p.hospitalListLevel / n.hospital_level) + 0.4 * p.preferredHospitalShare,
    underwriting: 0.7 * (1 - clamp(p.exclusionSeverities.reduce((a, v) => a + v, 0) / 10)) + 0.3 * (p.underwritingType === n.preferred_underwriting ? 1 : 0.5),
    insurer_quality: 0.5 * (1 - (s.n * s.upheldRate + 30 * 0.25) / (s.n + 30)) + 0.3 * s.finStrength + 0.2 * s.slaScore,
    process_ease: clamp(1 - 0.6 * p.docsUnavailable / Math.max(1, p.docsRequired) - 0.4 * Math.min(p.turnaroundDays / 14, 1)),
    terms_clarity: clamp(0.5 * p.ipidCompleteness + 0.3 * p.plainLanguage + 0.2 * (1 - Math.min(p.exclusionsCount / 20, 1))),
  };
  const keys = Object.keys(u), fit = keys.reduce((a, c) => a + w[c] * u[c], 0);
  const plus = Math.sqrt(keys.reduce((a, c) => a + w[c] * (1 - u[c]) ** 2, 0));
  const minus = Math.sqrt(keys.reduce((a, c) => a + w[c] * u[c] ** 2, 0));
  return { utilities: u, score: 100 * (0.7 * fit + 0.3 * minus / (plus + minus)) };
});
process.stdout.write(JSON.stringify(output));
