"""Export the implemented API schema without starting the app or seeding a DB."""

import json
import sys
from pathlib import Path
from copy import deepcopy

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "services/api"))
from app.main import app  # noqa: E402
from tools.mock_core import app as core_app  # noqa: E402


def contract(application, port):
    schema = deepcopy(application.openapi())
    schema["info"].update(
        {
            "description": "Implemented Helm prototype API. Local fixtures are fictional; live service acceptance is separate.",
            "contact": {
                "name": "Helm Broker project",
                "url": "https://github.com/Utkarsh2294/Helm_AI_Broker",
            },
            "license": {"name": "UNLICENSED"},
        }
    )
    schema["servers"] = [{"url": f"http://localhost:{port}", "description": "Local prototype"}]
    schema.setdefault("components", {}).setdefault("schemas", {})["Problem"] = {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "title": {"type": "string"},
            "detail": {"type": "string"},
            "status": {"type": "integer", "minimum": 400, "maximum": 599},
        },
        "additionalProperties": True,
    }
    tags = set()
    for path, methods in schema["paths"].items():
        section = next((part for part in path.split("/") if part and part not in ("api", "v1")), "health")
        tag = section.replace("-", " ").replace("_", " ").title()
        for method, operation in methods.items():
            if method not in ("get", "put", "post", "delete", "patch", "options", "head"):
                continue
            operation.setdefault("tags", [tag])
            tags.update(operation["tags"])
            operation.setdefault("description", operation.get("summary", "Helm API operation") + ".")
            for status, meaning in (
                (400, "Invalid request"),
                (401, "Authentication required"),
                (403, "Action prohibited"),
                (404, "Resource not found"),
                (409, "State or version conflict"),
                (422, "Validation failed"),
            ):
                operation.setdefault("responses", {}).setdefault(
                    str(status),
                    {
                        "description": meaning,
                        "content": {
                            "application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}
                        },
                    },
                )
    schema["tags"] = [{"name": tag, "description": f"{tag} operations."} for tag in sorted(tags)]
    return schema


target = root / "packages/contracts"
for name, application, port in (("broker", app, 8010), ("core", core_app, 8011)):
    content = json.dumps(contract(application, port), indent=2) + "\n"
    # JSON is a YAML 1.2 subset; either format's tooling can read these contracts.
    (target / f"{name}.yaml").write_text(content, encoding="utf-8")
    if name == "broker":
        (target / "broker.openapi.json").write_text(content, encoding="utf-8")
    else:
        (target / "openapi.yaml").write_text(content, encoding="utf-8")
print(target)
