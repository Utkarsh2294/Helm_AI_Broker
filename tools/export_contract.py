"""Export the implemented API schema without starting the app or seeding a DB."""

import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "services/api"))
from app.main import app  # noqa: E402
from tools.mock_core import app as core_app  # noqa: E402

target = root / "packages/contracts/broker.openapi.json"
target.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
for name, application in (("broker", app), ("core", core_app)):
    # JSON is a YAML 1.2 subset; these contracts can be read by either format's tooling.
    (target.parent / f"{name}.yaml").write_text(
        json.dumps(application.openapi(), indent=2) + "\n", encoding="utf-8"
    )
print(target)
