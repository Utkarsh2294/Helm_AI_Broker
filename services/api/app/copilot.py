import re


def answer_question(ranking, question):
    rows = ranking["top"]
    match = re.search(r"#(\d+)\s+above\s+#(\d+)", question, re.I)
    if match:
        left, right = (int(value) - 1 for value in match.groups())
        if 0 <= left < len(rows) and 0 <= right < len(rows):
            differences = sorted(
                ((c, rows[left]["points"][c] - rows[right]["points"][c]) for c in ranking["weights"]),
                key=lambda pair: -abs(pair[1]),
            )[:3]
            return {
                "answer": "Recorded point differences: "
                + "; ".join(f"{c.replace('_', ' ')} {value:+.1f}" for c, value in differences),
                "cited_fields": [f"{ranking['id']}.top[{i}].points" for i in (left, right)],
            }
    match = re.search(r"driving\s+#(\d+)", question, re.I)
    if match and 0 < int(match[1]) <= len(rows):
        index = int(match[1]) - 1
        points = sorted(rows[index]["points"].items(), key=lambda pair: -pair[1])[:3]
        return {
            "answer": "; ".join(f"{key.replace('_', ' ')}: {value:.1f} points" for key, value in points),
            "cited_fields": [f"{ranking['id']}.top[{index}].points"],
        }
    if "fewest documents" in question.lower() and rows:
        row = min(rows, key=lambda r: (r["plan"]["docsRequired"], r["plan"]["id"]))
        return {
            "answer": f"{row['plan']['name']} requires {row['plan']['docsRequired']} documents.",
            "cited_fields": [f"{row['plan']['id']}.docsRequired"],
        }
    return {
        "answer": "I can answer questions about the recorded ranking only. Check the plan terms and ask the broker about medical underwriting.",
        "cited_fields": [],
    }
