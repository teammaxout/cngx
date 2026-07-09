#!/usr/bin/env python3
"""Live security probes for cngx tracker AWS surface. No secrets in output."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BUCKET = "cngx-tracker-239143557891-us-east-1"
REGION = "us-east-1"
SUBMIT_URL = "https://d2m4128rn1m95q.cloudfront.net/submit"
INDEX_URL = f"https://{BUCKET}.s3.{REGION}.amazonaws.com/community/index.json"
BUCKET_URL = f"https://{BUCKET}.s3.{REGION}.amazonaws.com/"


def _req(method: str, url: str, data: bytes | None = None, headers: dict | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read(500).decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read(500).decode("utf-8", errors="replace")
        return exc.code, body


def main() -> int:
    results: dict[str, str] = {}

    code, _ = _req("GET", INDEX_URL)
    results["s3_get_index"] = f"{code} (expect 200)"
    assert code == 200, results

    code, _ = _req("GET", BUCKET_URL)
    results["s3_list_bucket"] = f"{code} (expect 403)"
    assert code == 403, results

    code, _ = _req("PUT", f"{BUCKET_URL}community/evil-probe.json", data=b"{}")
    results["unauthenticated_put"] = f"{code} (expect 403)"
    assert code == 403, results

    code, _ = _req("GET", f"{BUCKET_URL}private-probe.json")
    results["s3_get_non_community"] = f"{code} (expect 403)"
    assert code in (403, 404), results

    bad = json.dumps({"prompt": "secret"}).encode()
    code, body = _req(
        "POST",
        SUBMIT_URL,
        data=bad,
        headers={"Content-Type": "application/json"},
    )
    results["submit_forbidden_key"] = f"{code} (expect 400)"
    assert code == 400, body

    # API Gateway throttling: burst of valid-shaped but invalid payloads
    def post_once(_: int) -> int:
        payload = json.dumps({"schema_version": 1, "nope": 1}).encode()
        code, _ = _req(
            "POST",
            SUBMIT_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        return code

    codes: list[int] = []
    with ThreadPoolExecutor(max_workers=60) as pool:
        futs = [pool.submit(post_once, i) for i in range(80)]
        for fut in as_completed(futs):
            codes.append(fut.result())
    throttle_hits = sum(1 for c in codes if c == 429)
    results["submit_burst_80"] = f"codes={sorted(set(codes))} 429_count={throttle_hits}"
    assert throttle_hits > 0 or 503 in codes, results

    # WAF rate limit: sustained cheap POSTs (invalid body, fast)
    waf_blocked = 0
    waf_total = 0
    for i in range(120):
        code, _ = _req(
            "POST",
            SUBMIT_URL,
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        waf_total += 1
        if code == 403:
            waf_blocked += 1
        if waf_blocked >= 3:
            break
        time.sleep(0.05)
    results["waf_probe"] = f"requests={waf_total} blocked_403={waf_blocked} (expect >=1 if limit hit)"
    assert waf_blocked >= 1, results

    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
