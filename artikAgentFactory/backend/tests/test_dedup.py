from app.services.pipeline.dedup import dedup, dedup_key, normalize_url


def test_normalize_url_strips_tracking_and_trailing_slash():
    a = normalize_url("https://Example.com/page/?utm_source=x&utm_medium=y&ref=z")
    b = normalize_url("https://example.com/page?ref=z")
    assert a == b


def test_normalize_url_strips_www_and_fragment():
    a = normalize_url("https://www.example.com/page#section")
    b = normalize_url("https://example.com/page")
    assert a == b


def test_normalize_url_http_vs_https_still_distinct_by_default():
    # scheme is preserved (not a tracked-noise param) — http and https are genuinely
    # different endpoints unless the site redirects, which we can't assume here.
    a = normalize_url("http://example.com/page")
    b = normalize_url("https://example.com/page")
    assert a != b


def test_dedup_key_stable_for_equivalent_urls():
    k1 = dedup_key("https://www.example.com/page/?utm_source=newsletter")
    k2 = dedup_key("https://example.com/page")
    assert k1 == k2


def test_dedup_merges_duplicates_keeping_higher_confidence():
    candidates = [
        {"url": "https://example.com/a?utm_source=x", "title": "A (low)", "confidence_score": 0.4},
        {"url": "https://example.com/a", "title": "A (high)", "confidence_score": 0.9},
        {"url": "https://example.com/b", "title": "B", "confidence_score": 0.5},
    ]
    result = dedup(candidates)
    assert len(result) == 2
    a = next(c for c in result if c["title"].startswith("A"))
    assert a["title"] == "A (high)"


def test_dedup_drops_candidates_with_no_url():
    candidates = [{"url": "", "title": "no url"}, {"url": "https://example.com/x", "title": "has url"}]
    result = dedup(candidates)
    assert len(result) == 1
    assert result[0]["title"] == "has url"
