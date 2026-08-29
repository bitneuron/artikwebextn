def test_security_headers_present_on_response(client):
    resp = client.get("/api/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "geolocation=()" in resp.headers.get("permissions-policy", "")
    csp = resp.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp


def test_request_id_header_present_and_echoed(client):
    resp = client.get("/api/health", headers={"X-Request-ID": "test-correlation-123"})
    assert resp.headers.get("x-request-id") == "test-correlation-123"

    resp2 = client.get("/api/health")
    assert resp2.headers.get("x-request-id")  # auto-generated when not supplied


def test_oversized_request_body_rejected(client):
    big_payload = {"padding": "x" * 2_000_000}
    resp = client.post("/api/agents", json=big_payload,
                       headers={"Content-Length": str(len(str(big_payload)))})
    assert resp.status_code == 413


def test_general_rate_limit_eventually_blocks(client):
    from app.core.security_middleware import _GENERAL_MAX_REQUESTS

    last_status = None
    for _ in range(_GENERAL_MAX_REQUESTS + 5):
        last_status = client.get("/api/health").status_code
        if last_status == 429:
            break
    assert last_status == 429
