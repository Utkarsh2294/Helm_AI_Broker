from datetime import timedelta
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import service, publication
from app.auth import hasher
from app.auth.mfa import challenge
from app.config import settings
from app.core_client.client import CoreAPIClient
from app.db.models import Base, Case, User, LoginSession, Job, Approval, Publication, utcnow
from app.db.store import make_engine, latest, save_snapshot
from app.agents.review import canonical_hash
from app.schemas import QuoteRequest, Needs, CoverageNeed
from tools.mock_core import app as core_app


def test_committed_approval_precedes_idempotent_core_delivery(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path / 'delivery.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings(), 'core_delivery_enabled', True)
    transport = httpx.ASGITransport(app=core_app)
    class DurableCore(CoreAPIClient):
        async def publish(self, case_id, approval_id, pack):
            with Session(engine) as independent:
                assert independent.get(Approval, approval_id), 'Core must never observe uncommitted approval'
            return await super().publish(case_id, approval_id, pack)
    monkeypatch.setattr(publication, 'CoreAPIClient', lambda: DurableCore(transport))
    with Session(engine, expire_on_commit=False) as db:
        user = User(email='pub@test.demo', name='Test', role='authorised_broker', fca_irn='TEST-IRN', can_approve=True, password_hash=hasher.hash('test'))
        db.add(user); db.flush()
        session = LoginSession(id='pub-session', user_id=user.id, csrf='c', expires_at=(utcnow() + timedelta(hours=1)).isoformat(), step_up_at=utcnow().isoformat())
        db.add(session)
        case = service.import_request(db, QuoteRequest(id='delivery', name='Fictional', needs=Needs(coverage={'cancer': CoverageNeed(level=3)})))
        service.act(db, case.id, 'sign-off', user, session, {'dnr_acknowledged': True})
        service.act(db, case.id, 'release', user, session, {})
        db.scalar(select(Job).where(Job.kind == 'collect_quotes')).due_at = utcnow().isoformat()
        db.flush(); service.process_due_jobs(db)
        ranking = latest(db, case.id, 'ranking').body
        selected = [r['plan']['id'] for r in ranking['top'][:3]]
        service.act(db, case.id, 'selection', user, session, {'ranking_id': ranking['id'], 'selected': selected, 'survey': {'thumbs': dict.fromkeys(selected, 'up')}, 'acknowledgements': selected})
        pack = {**latest(db, case.id, 'pack').body, 'dnr_sections_confirmed': ['priorities', 'coverage', 'budget', 'household', 'medical_flag']}
        pack['unmet_needs_addressed'] = [f"{n['plan_id']}:{n['need']}" for n in pack['unmet_needs']]
        pack['pack_hash'] = canonical_hash({k: v for k, v in pack.items() if k != 'pack_hash'})
        save_snapshot(db, case.id, 'pack', pack)
        proof = challenge(db, user.id, 'step-up', {'session_id': session.id})
        db.flush()
        queued = service.act(db, case.id, 'approve', user, session, {'pack_hash': pack['pack_hash'], 'step_up_token': proof})
        assert queued['state'] == 'AWAIT_APPROVAL' and queued['delivery_pending']
        assert not db.scalar(select(Publication))
        db.commit()
        service.process_due_jobs(db); db.commit()
        assert case.state == 'PUBLISHED'
        delivered = latest(db, case.id, 'publication').body
        original = db.scalar(select(Publication))
        service.process_due_jobs(db); db.commit()
        assert db.scalar(select(Publication)).id == original.id
        async def use_link_once():
            async with httpx.AsyncClient(transport=transport, base_url='http://core') as client:
                path = httpx.URL(delivered['magic_link']).raw_path.decode()
                assert (await client.get(path)).status_code == 200
                assert (await client.get(path)).status_code == 410
        import asyncio
        asyncio.run(use_link_once())
    engine.dispose()
