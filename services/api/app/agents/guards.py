import re

FORBIDDEN = re.compile(
    r"you should buy|best for you|will cover|won.t cover|suitable for|guaranteed|ideal for|perfect for", re.I
)


def numeric_values(value):
    if isinstance(value, dict):
        return [n for item in value.values() for n in numeric_values(item)]
    if isinstance(value, list):
        return [n for item in value for n in numeric_values(item)]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [float(value)]
    return []


def grounded(text, facts):
    allowed = numeric_values(facts)
    allowed += [v * 100 for v in allowed] + [v / 100 for v in allowed]
    numbers = [float(n.replace(",", "")) for n in re.findall(r"(?<!\w)-?\d[\d,]*(?:\.\d+)?", text)]
    return not FORBIDDEN.search(text) and all(
        any(abs(n - value) <= 0.051 for value in allowed) for n in numbers
    )


def consumer_draft(plan):
    return (
        f"This plan costs £{plan['annualPremiumPence'] / 100:.2f} a year. "
        f"Your excess is £{plan['excessPence'] / 100:.2f}. "
        f"Its hospital list is level {plan['hospitalListLevel']}. "
        "Read the policy terms and ask your broker about any gaps."
    )
