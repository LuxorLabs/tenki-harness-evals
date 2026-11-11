from harness_evals.cli import _missing_env


def _clear(monkeypatch):
    for var in ("LUXORAI_API_KEY", "TENKI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_api_key_required(monkeypatch):
    _clear(monkeypatch)
    assert _missing_env([]) == ["TENKI_API_KEY"]


def test_luxorai_api_key_accepted(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LUXORAI_API_KEY", "lx_test")
    assert _missing_env([]) == []


def test_tenki_api_key_still_accepted(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("TENKI_API_KEY", "tk_test")
    assert _missing_env([]) == []
