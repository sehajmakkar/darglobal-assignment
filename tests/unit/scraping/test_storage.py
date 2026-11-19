from pathlib import Path

from dgbot.scraping.storage import RawStore, key_for


def test_keys_are_readable_safe_and_distinguish_case_variants() -> None:
    a = key_for("https://darglobal.co.uk/La-Collina")
    b = key_for("https://darglobal.co.uk/la-collina")

    assert a.startswith("la-collina-")
    assert a != b
    assert all(c.isalnum() or c == "-" for c in a)


def test_root_url_gets_a_key() -> None:
    assert key_for("https://darglobal.co.uk/").startswith("root-")


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    store = RawStore(tmp_path, "darglobal")
    url = "https://darglobal.co.uk/the-astera"

    assert not store.has(url)
    meta = store.save(url, b"<html>hi</html>", status=200, method="browser", kind="page")

    assert store.has(url)
    loaded = store.load_meta(url)
    assert loaded == meta
    assert store.load_body(loaded) == b"<html>hi</html>"
    assert loaded.bytes == 15 and len(loaded.sha256) == 64
    assert [m.url for m in store.iter_meta()] == [url]
