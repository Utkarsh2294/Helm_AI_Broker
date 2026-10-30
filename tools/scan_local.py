"""Passive ZAP inspection of the fictional Compose deployment; no active scan."""

import json
import ipaddress
import os
import re
import secrets
import subprocess
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4
import httpx


ZAP_IMAGE = "zaproxy/zap-bare@sha256:99575ac0542e9b424177589d70720c0426ca410005812d3c10bd16370bbb4f54"


def inspect_zap(scanner_url, key):
    with httpx.Client(base_url=scanner_url, timeout=3, trust_env=False) as control:

        def view(path):
            response = control.get("/JSON/" + path + "/", params={"apikey": key})
            response.raise_for_status()
            return response.json()

        readiness_error = "No response"
        for attempt in range(150):
            try:
                version = view("core/view/version")["version"]
                break
            except (httpx.HTTPError, ValueError, KeyError) as error:
                readiness_error = (
                    f"HTTP {error.response.status_code}"
                    if isinstance(error, httpx.HTTPStatusError)
                    else type(error).__name__
                )
                time.sleep(1)
        else:
            raise RuntimeError("Local ZAP daemon did not become ready: " + readiness_error)
        statuses = []
        with httpx.Client(proxy=scanner_url, timeout=45, follow_redirects=True, trust_env=False) as client:
            web_headers = {"Host": "localhost:5184"}
            web = client.get("http://web:5180/", headers=web_headers)
            web.raise_for_status()
            if "Broker workspace" not in web.text:
                raise RuntimeError("Proxy did not return the broker frontend")
            statuses.append(web.status_code)
            assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', web.text)
            for asset in assets[:20]:
                statuses.append(client.get("http://web:5180" + asset, headers=web_headers).status_code)
            login = client.post(
                "http://api:8010/api/v1/auth/password",
                json={"email": "broker@helm.demo", "password": "HelmDemo!2026"},
            )
            login.raise_for_status()
            statuses.append(login.status_code)
            paths = [
                "/health",
                "/api/v1/auth/session",
                "/api/v1/auth/devices",
                "/api/v1/cases?limit=50",
                "/api/v1/partners",
                "/api/v1/insights",
                "/api/v1/audit/search",
            ]
            for path in paths:
                response = client.get("http://api:8010" + path)
                response.raise_for_status()
                statuses.append(response.status_code)
            cases = client.get("http://api:8010/api/v1/cases?limit=3").json()["items"]
            for case in cases:
                for suffix in ("", "/ratings", "/events"):
                    response = client.get("http://api:8010/api/v1/cases/" + case["id"] + suffix)
                    response.raise_for_status()
                    statuses.append(response.status_code)
        for attempt in range(120):
            if int(view("pscan/view/recordsToScan")["recordsToScan"]) == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Passive scan did not drain")
        alerts = view("core/view/alerts")["alerts"]
        findings = {
            str(a["pluginId"]): {
                "id": a["pluginId"],
                "name": a["alert"],
                "risk": a["risk"],
                "confidence": a["confidence"],
            }
            for a in alerts
        }
        counts = dict(Counter(item["risk"] for item in findings.values()))
        result = {
            "scanner": "OWASP ZAP",
            "version": version,
            "image": ZAP_IMAGE,
            "scope": "Local fictional Compose web and authenticated API; passive traffic inspection only",
            "requests_exercised": len(statuses),
            "all_exercised_responses_200": all(status == 200 for status in statuses),
            "counts_by_risk": counts,
            "findings": list(findings.values()),
            "high_critical_clear": not any(counts.get(level, 0) for level in ("High", "Critical")),
            "independent_penetration_test": False,
        }
        return result


def scan(output="docs/verification/zap-passive.json"):
    image = ZAP_IMAGE
    name = "helm-zap-qa-" + uuid4().hex[:12]
    key = secrets.token_urlsafe(32)
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            name,
            "--network",
            "helmaibroker_default",
            "-e",
            "JAVA_OPTS=-Xmx512m",
            image,
            "zap.sh",
            "-daemon",
            "-silent",
            "-host",
            "0.0.0.0",
            "-port",
            "8090",
            "-config",
            "api.key=" + key,
            "-config",
            "api.addrs.addr.name=.*",
            "-config",
            "api.addrs.addr.regex=true",
            "-config",
            "autoupdate.checkOnStart=false",
            "-config",
            "autoupdate.installAddonUpdates=false",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    container_id = started.stdout.strip()
    if not re.fullmatch("[a-f0-9]{64}", container_id):
        raise RuntimeError("Unexpected scanner container identity")
    try:
        # Run the client on the same private network. This avoids Windows/WSL
        # port-forwarding resets and publishes no scanner port on the host.
        address = subprocess.check_output(
            [
                "docker",
                "inspect",
                "--format",
                '{{(index .NetworkSettings.Networks "helmaibroker_default").IPAddress}}',
                container_id,
            ],
            text=True,
        ).strip()
        if not ipaddress.ip_address(address).is_private:
            raise RuntimeError("Scanner must be on the private Compose network")
        context = json.dumps({"url": f"http://{address}:8090", "key": key})
        prefix = "import os\nos.environ['HELM_ZAP_INTERNAL'] = " + repr(context) + "\n"
        completed = subprocess.run(
            ["docker", "exec", "-i", "helmaibroker-api-1", "python", "-"],
            input=prefix + Path(__file__).read_text(encoding="utf-8"),
            text=True,
            capture_output=True,
            timeout=300,
        )
        if completed.returncode:
            raise RuntimeError(
                "Internal passive scan failed: " + completed.stderr[-1000:].replace(key, "[scanner-key]")
            )
        result = json.loads(completed.stdout)
        Path(output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))
        if not result["high_critical_clear"]:
            raise RuntimeError("High/critical passive findings require a fix")
    finally:
        subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, check=False)


if __name__ == "__main__":
    if os.environ.get("HELM_ZAP_INTERNAL"):
        context = json.loads(os.environ["HELM_ZAP_INTERNAL"])
        print(json.dumps(inspect_zap(context["url"], context["key"])))
    else:
        scan()
