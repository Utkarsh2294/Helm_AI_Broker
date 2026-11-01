"""Run the same aggregate/association jobs used by the scheduled worker."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/api"))
from app.db.store import SessionLocal  # noqa: E402
from app.copilot_jobs import refresh_daily_view, detect_aging  # noqa: E402
from app.broker_insights import compute_drivers  # noqa: E402

if __name__ == "__main__":
    with SessionLocal() as db:
        refresh_daily_view(db)
        compute_drivers(db)
        detect_aging(db)
        db.commit()
    print("Saved operational projections refreshed. No advice, policy or approval was changed.")
