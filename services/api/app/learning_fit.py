"""Bradley–Terry MAP fit with Armijo line search and evidence shrinkage."""
import math
from app.schemas import CRITERIA


def softmax(logits):
    exps = {c: math.exp(logits[c] - max(logits.values())) for c in CRITERIA}
    return {c: exps[c] / sum(exps.values()) for c in CRITERIA}


def fit_bradley_terry(pairs, prior, max_iter=200, tolerance=1e-6):
    log_prior = {c: math.log(prior[c]) for c in CRITERIA}
    logits = dict(log_prior)
    def objective(values):
        w = softmax(values)
        likelihood = 0
        for pair in pairs:
            z = 8 * sum(w[c] * (pair["preferred"][c] - pair["other"][c]) for c in CRITERIA)
            likelihood -= pair["weight"] * math.log1p(math.exp(-max(-700, min(700, z))))
        return likelihood - 0.5 * sum((values[c] - log_prior[c]) ** 2 for c in CRITERIA)
    iterations = 0
    for iterations in range(max_iter):
        w = softmax(logits)
        gradient = {c: -(logits[c] - log_prior[c]) for c in CRITERIA}
        for pair in pairs:
            diff = {c: pair["preferred"][c] - pair["other"][c] for c in CRITERIA}
            linear = sum(w[c] * diff[c] for c in CRITERIA)
            probability = 1 / (1 + math.exp(max(-700, min(700, -8 * linear))))
            for c in CRITERIA:
                gradient[c] += pair["weight"] * (1 - probability) * 8 * w[c] * (diff[c] - linear)
        norm = sum(v * v for v in gradient.values())
        if math.sqrt(norm) < tolerance:
            break
        step, baseline = 0.1, objective(logits)
        while step > 1e-12:
            candidate = {c: logits[c] + step * gradient[c] for c in CRITERIA}
            if objective(candidate) >= baseline + 0.1 * step * norm:
                break
            step /= 2
        if step <= 1e-12:
            break
        logits = candidate
    fitted = softmax(logits)
    shrinkage = len(pairs) / (len(pairs) + 50)
    return {"weights": {c: shrinkage * fitted[c] + (1 - shrinkage) * prior[c] for c in CRITERIA},
            "iterations": iterations + 1, "evidence_factor": shrinkage}
