import httpx
import pytest
from app.core_client.client import CoreAPIClient
from tools.mock_core import app, catalogue


@pytest.mark.anyio
async def test_mock_contract_and_idempotent_approved_delivery():
    client = CoreAPIClient(transport=httpx.ASGITransport(app=app))
    assert len(catalogue()) == 30
    listed = await client.request("GET", "/v1/quote-requests")
    assert len(listed["items"]) == 3
    assert (await client.get_quote_request("core-1"))["cover_type"] == "family"
    first = await client.publish("case", "approval", {"pack_hash": "abc"})
    again = await client.publish("case", "approval", {"pack_hash": "abc"})
    assert first == again and first["demo"] and not first["magic_link_sent"]
