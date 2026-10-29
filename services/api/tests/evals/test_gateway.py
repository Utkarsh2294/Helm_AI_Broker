import pytest
import fakeredis
from sqlalchemy.orm import Session
from app.db.models import Base
from app.db.store import make_engine
from app.llm.gateway import LLMGateway
from app.llm.redaction import RedactionService
from app.schemas import DomainError


@pytest.mark.anyio
async def test_gateway_canary_redaction_and_provider_denial(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'gateway.db'}")
    Base.metadata.create_all(engine)
    fake = fakeredis.FakeRedis()
    sent = []
    async def model(**kwargs):
        sent.append(kwargs)
        return {"choices": [{"message": {"content": "The broker must review the stated needs."}}]}
    with Session(engine) as db:
        gateway = LLMGateway(fake, db, completion=model)
        await gateway.call([{"role": "user", "content": "Asha Patel email asha@example.test DOB 1988-04-02 canary-medical"}],
            "canary", "test", identifiers=["Asha Patel"], medical_texts=["canary-medical"])
        prompt = str(sent)
        assert all(secret not in prompt for secret in ["Asha Patel", "asha@example.test", "1988-04-02", "canary-medical"])
        with pytest.raises(DomainError):
            await gateway.call([], "canary", "test", model="unknown/model")
        mapping = fake.get("helm:redaction:canary")
        assert b"Asha Patel" not in mapping
