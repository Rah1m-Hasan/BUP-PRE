def test_cache_key_stable():
    from app.services.cache import TTLCache

    p1 = {"a": 1, "b": [1, 2]}
    p2 = {"b": [1, 2], "a": 1}
    assert TTLCache.key(p1) == TTLCache.key(p2)


def test_cache_put_get():
    from app.services.cache import TTLCache

    c = TTLCache(ttl_seconds=60, max_entries=10)
    c.put("k1", {"x": 1})
    assert c.get("k1") == {"x": 1}
    assert c.get("nope") is None


def test_cache_eviction():
    from app.services.cache import TTLCache

    c = TTLCache(ttl_seconds=60, max_entries=2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)
    assert c.get("a") is None
    assert c.get("b") == 2
    assert c.get("c") == 3
