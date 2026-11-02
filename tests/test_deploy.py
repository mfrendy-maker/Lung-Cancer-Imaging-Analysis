import threading
from http.server import HTTPServer
from pathlib import Path

import requests

from lung_imaging_analysis import lung_gui

ROOT = Path(__file__).resolve().parents[1]


def test_healthz_works_without_the_access_code(monkeypatch):
    monkeypatch.setenv("LUNG_GUI_TOKEN", "a-long-random-code")
    server = HTTPServer(("127.0.0.1", 0), lung_gui.LungGUIHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        assert requests.get(base + "/healthz", timeout=10).text == "ok"
        assert requests.get(base + "/", timeout=10).status_code == 401
    finally:
        server.shutdown()
        server.server_close()


def test_deploy_files_are_consistent():
    docker = (ROOT / "Dockerfile").read_text()
    render = (ROOT / "render.yaml").read_text()
    assert "lung_imaging_analysis.lung_gui" in docker and "LUNG_GUI_DEMO=1" in docker
    assert "healthCheckPath: /healthz" in render and "generateValue: true" in render
    assert "LUNG_GUI_TOKEN" in render
