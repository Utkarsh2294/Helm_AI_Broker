import base64
from test_governance_access import login


def test_document_upload_and_read_are_scoped_encrypted_consented_and_not_sent_to_models(client):
    headers = login(client, "broker@helm.demo")
    case = client.post(
        "/api/v1/demo/requests",
        headers=headers,
        json={
            "id": "document-fixture",
            "name": "Demo document owner",
            "needs": {"coverage": {"cancer": {"level": 3}}},
        },
    ).json()
    url = "/api/v1/cases/" + case["id"]
    body = {
        "mime": "text/plain",
        "content_base64": base64.b64encode(b"PRIVATE_DOCUMENT_CANARY - verbatim notes").decode(),
    }
    assert client.post(url + "/documents", headers=headers, json=body).status_code == 403
    proof = client.post("/api/v1/auth/step-up", headers=headers, json={"password": "HelmDemo!2026"}).json()[
        "step_up_token"
    ]
    assert client.post(url + "/medical-access", headers={**headers, "X-Step-Up": proof}).status_code == 200
    created = client.post(url + "/documents", headers=headers, json=body)
    assert created.status_code == 200, created.text
    assert created.json()["needs_broker_verification"]
    assert client.post(url + "/documents", headers=headers, json=body).json()["duplicate"]
    listed = client.get(url + "/documents")
    assert "PRIVATE_DOCUMENT_CANARY" not in listed.text
    content_url = url + "/documents/" + created.json()["id"]
    assert client.get(content_url).content == b"PRIVATE_DOCUMENT_CANARY - verbatim notes"
    assert "PRIVATE_DOCUMENT_CANARY" not in client.get(url).text
    assert (
        client.post(
            url + "/documents",
            headers=headers,
            json={**body, "content_base64": base64.b64encode(b"\xff").decode()},
        ).status_code
        == 422
    )
    login(client, "assistant@helm.demo")
    assert client.get(content_url).status_code == 403
