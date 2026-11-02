import io
import threading
from http.server import HTTPServer

import numpy as np
import requests
from PIL import Image

from lung_imaging_analysis import image_analysis, lung_gui


def _chest(lesion_radius: int | None = 9, vessel: bool = False) -> np.ndarray:
    y, x = np.ogrid[:256, :256]
    img = np.zeros((256, 256), dtype=np.uint8)
    img[((x - 128) / 115) ** 2 + ((y - 128) / 90) ** 2 <= 1] = 150
    for cx in (85, 171):
        img[((x - cx) / 40) ** 2 + ((y - 128) / 65) ** 2 <= 1] = 40
    if lesion_radius:
        img[(x - 190) ** 2 + (y - 140) ** 2 <= lesion_radius**2] = 200
    if vessel:
        img[100:160, 180:182] = 170
    return img


def _png(arr: np.ndarray) -> bytes:
    out = io.BytesIO()
    Image.fromarray(arr).save(out, format="PNG")
    return out.getvalue()


def test_lesion_is_marked_with_size_and_severity():
    _, items = image_analysis.detect_2d(_chest(), 0.7)
    assert len(items) == 1
    finding = items[0][1]
    assert abs(finding.x - 190) <= 3 and abs(finding.y - 140) <= 3
    assert 10 <= finding.diameter_mm <= 15
    assert finding.severity == "high"


def test_large_lesion_touching_the_pleura_is_marked_critical():
    img = _chest(lesion_radius=None)
    y, x = np.ogrid[:256, :256]
    img[(x - 100) ** 2 + (y - 170) ** 2 <= 14**2] = 200
    _, items = image_analysis.detect_2d(img, 0.7)
    assert [f.severity for _, f in items] == ["critical"]


def test_clean_chest_has_no_findings():
    _, items = image_analysis.detect_2d(_chest(lesion_radius=None), 0.7)
    assert items == []


def test_thin_vessel_is_not_marked():
    _, items = image_analysis.detect_2d(_chest(lesion_radius=None, vessel=True), 0.7)
    assert items == []


def test_analyse_upload_returns_annotated_png():
    result = image_analysis.analyse_upload("chest.png", _png(_chest()), 0.7)
    assert result["severity"] == "high"
    assert result["images"][0].startswith(b"\x89PNG")
    assert Image.open(io.BytesIO(result["images"][0])).width > 256


def test_invalid_inputs_are_rejected():
    for bad in (lambda: image_analysis.analyse_upload("x.png", b"not an image"),
                lambda: image_analysis.analyse_upload("x.png", _png(_chest()), 99.0)):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError("expected ValueError")


def test_gui_upload_roundtrip():
    server = HTTPServer(("127.0.0.1", 0), lung_gui.LungGUIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        assert requests.get(base + "/", timeout=10).status_code == 200
        response = requests.post(
            base + "/analyse",
            files={"image": ("<script>chest.png", _png(_chest()), "image/png")},
            data={"spacing": "0.7"},
            timeout=60,
        )
        assert response.status_code == 200
        assert "data:image/png;base64" in response.text
        assert "HIGH" in response.text
        assert "<script>chest" not in response.text
        bad = requests.post(base + "/analyse", files={"image": ("x.png", b"junk", "image/png")}, timeout=10)
        assert bad.status_code == 400
    finally:
        server.shutdown()
        server.server_close()
