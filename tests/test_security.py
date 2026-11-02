import io
import threading
from http.server import HTTPServer

import numpy as np
import requests
from PIL import Image

from lung_imaging_analysis import lung_gui, security

EMPTY = {"label": "x", "severity": "none", "dominant_finding": None, "findings": [], "images": [], "notes": []}


def _chest_png() -> bytes:
    y, x = np.ogrid[:256, :256]
    img = np.zeros((256, 256), dtype=np.uint8)
    img[((x - 128) / 115) ** 2 + ((y - 128) / 90) ** 2 <= 1] = 150
    for cx in (85, 171):
        img[((x - cx) / 40) ** 2 + ((y - 128) / 65) ** 2 <= 1] = 40
    out = io.BytesIO()
    Image.fromarray(img).save(out, format="PNG")
    return out.getvalue()


class _Server:
    def __enter__(self):
        self.server = HTTPServer(("127.0.0.1", 0), lung_gui.LungGUIHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def _upload(session, base):
    return session.post(base + "/analyse", files={"image": ("c.png", _chest_png(), "image/png")},
                        data={"spacing": "0.7"}, timeout=60, allow_redirects=False)


def test_token_protects_the_tool(monkeypatch):
    monkeypatch.setenv("LUNG_GUI_TOKEN", "a-long-random-code")
    monkeypatch.setattr(lung_gui, "_LIMITER", security.RateLimiter())
    with _Server() as s:
        anon = requests.Session()
        assert anon.get(s.base + "/", timeout=10).status_code == 401
        assert _upload(anon, s.base).status_code == 401
        assert anon.post(s.base + "/login", data={"token": "wrong"}, allow_redirects=False, timeout=10).status_code == 401

        ok = requests.Session()
        login = ok.post(s.base + "/login", data={"token": "a-long-random-code"}, allow_redirects=False, timeout=10)
        assert login.status_code == 303
        assert "HttpOnly" in login.headers["Set-Cookie"] and "SameSite=Strict" in login.headers["Set-Cookie"]
        assert ok.get(s.base + "/", timeout=10).status_code == 200
        assert _upload(ok, s.base).status_code == 200


def test_login_attempts_are_rate_limited(monkeypatch):
    monkeypatch.setenv("LUNG_GUI_TOKEN", "a-long-random-code")
    monkeypatch.setattr(lung_gui, "_LIMITER", security.RateLimiter())
    with _Server() as s:
        codes = [requests.post(s.base + "/login", data={"token": "x"}, timeout=10).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and 429 in codes[5:]


def test_security_headers_and_size_limit(monkeypatch):
    monkeypatch.setenv("LUNG_GUI_MAX_MB", "0.001")
    monkeypatch.setattr(lung_gui, "_LIMITER", security.RateLimiter())
    with _Server() as s:
        home = requests.get(s.base + "/", timeout=10)
        assert home.headers["X-Frame-Options"] == "DENY"
        assert "default-src 'none'" in home.headers["Content-Security-Policy"]
        assert home.headers["Cache-Control"] == "no-store"
        assert _upload(requests.Session(), s.base).status_code == 413


def test_analysis_requests_are_rate_limited(monkeypatch):
    monkeypatch.setenv("LUNG_GUI_RATE", "1")
    monkeypatch.setattr(lung_gui, "_LIMITER", security.RateLimiter())
    with _Server() as s:
        session = requests.Session()
        assert _upload(session, s.base).status_code == 200
        assert _upload(session, s.base).status_code == 429


def test_demo_mode_never_saves_and_hides_consent(monkeypatch, tmp_path):
    monkeypatch.setenv("LUNG_GUI_DEMO", "1")
    monkeypatch.setattr(lung_gui, "TRAINING_DIR", tmp_path / "t")
    page = lung_gui.render_upload_page()
    assert 'name="training_consent"' not in page and "never saved" in page and 'id="go"' in page
    assert lung_gui.store_training_upload("a.png", b"x", 0.7, {"training_consent": "yes"}) is None
    assert not (tmp_path / "t").exists()


def test_saved_uploads_are_capped(monkeypatch, tmp_path):
    monkeypatch.setenv("LUNG_GUI_MAX_STORE_MB", "0.0001")
    monkeypatch.setattr(lung_gui, "TRAINING_DIR", tmp_path / "t")
    assert lung_gui.store_training_upload("a.png", b"x" * 500, 0.7, {"training_consent": "yes"}) is None


def test_open_exposure_requires_a_token(monkeypatch):
    monkeypatch.delenv("LUNG_GUI_TOKEN", raising=False)
    monkeypatch.delenv("LUNG_GUI_ALLOW_OPEN", raising=False)
    assert security.refuse_open_exposure("127.0.0.1") is None
    assert "LUNG_GUI_TOKEN" in security.refuse_open_exposure("0.0.0.0")
    monkeypatch.setenv("LUNG_GUI_TOKEN", "abc")
    assert security.refuse_open_exposure("0.0.0.0") is None


def test_result_page_has_pdf_print_option():
    page = lung_gui.render_result("a.png", EMPTY)
    assert "window.print()" in page and "Save as PDF" in page
    assert "@page" in page and "Report generated" in page
