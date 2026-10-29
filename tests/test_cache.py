import hashlib

from aftermath.cache import ResponseCache, file_digest, request_key


def test_request_key_ignores_key_order():
    assert request_key({"model": "m", "prompt": "door"}) == request_key({"prompt": "door", "model": "m"})


def test_request_key_changes_with_any_value():
    assert request_key({"prompt": "door"}) != request_key({"prompt": "doors"})


def test_file_digest_is_sha256_of_contents(tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"\xff\xd8 not really a jpeg")
    assert file_digest(path) == hashlib.sha256(b"\xff\xd8 not really a jpeg").hexdigest()


def test_fetch_computes_once_then_replays(tmp_path):
    cache = ResponseCache(tmp_path)
    calls = []

    def compute():
        calls.append(1)
        return {"boxes": [[1, 2, 3, 4]]}

    request = {"backend": "test", "prompt": "rating plate"}
    first = cache.fetch(request, compute)
    second = cache.fetch(request, compute)

    assert calls == [1]
    assert first["result"] == second["result"] == {"boxes": [[1, 2, 3, 4]]}
    assert second["request"] == request
    assert (cache.hits, cache.misses) == (1, 1)


def test_records_survive_a_new_cache_instance(tmp_path):
    request = {"backend": "test", "prompt": "door"}
    ResponseCache(tmp_path).fetch(request, lambda: [0.9])
    assert ResponseCache(tmp_path).get(request)["result"] == [0.9]


def test_put_leaves_no_temporary_files(tmp_path):
    cache = ResponseCache(tmp_path)
    cache.put({"prompt": "generator"}, "ok", 0.5)
    files = [p.name for p in tmp_path.rglob("*") if p.is_file()]
    assert files == [cache.path({"prompt": "generator"}).name]
