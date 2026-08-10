import urllib.parse

from scripts import wp15_public_surface as surface


def responses(profile: str):
    release = surface.RELEASES[profile]
    oauth = "https://accounts.feishu.cn/open-apis/authen/v1/authorize?" + urllib.parse.urlencode(
        {"redirect_uri": "https://journey.muchenai.com/auth/feishu/callback", "state": "never-output"}
    )
    values = {
        "/": (200, {}, b"home"),
        "/health/ready": (200, {}, (f'{{"status":"ready","release":"{release}"}}').encode()),
        "/ops": (401, {}, b""),
        "/review": (401, {}, b""),
        "/auth/feishu?return_to=%2Fops": (303, {"Location": oauth}, b""),
        "/content": (303, {"Location": "/content/login", "Cache-Control": "private, no-store"}, b""),
        "/content/login": (200, {}, "使用飞书进入".encode()),
    }
    return values


def test_cutover_surface_checks_all_nine_observable_contracts(monkeypatch, capsys) -> None:
    values = responses("cutover")
    monkeypatch.setattr(surface, "request", lambda path: values[path])
    assert surface.check(1, "cutover") is True
    output = capsys.readouterr().out
    for check in (
        "root",
        "readiness",
        "ops_denied",
        "review_denied",
        "content_redirect",
        "content_cache",
        "content_login",
        "content_login_cta",
        "feishu_oauth",
    ):
        assert f"check={check} result=PASS" in output
    assert "never-output" not in output


def test_baseline_surface_skips_new_content_contract(monkeypatch, capsys) -> None:
    values = responses("baseline")
    monkeypatch.setattr(surface, "request", lambda path: values[path])
    assert surface.check(1, "baseline") is True
    output = capsys.readouterr().out
    assert "check=feishu_oauth result=PASS" in output
    assert "content_login" not in output
