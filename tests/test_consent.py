import json

from lung_imaging_analysis import lung_gui

EMPTY = {"label": "x", "severity": "none", "dominant_finding": None, "findings": [], "images": [], "notes": []}


def test_consent_checkbox_is_optional_and_unchecked():
    assert 'name="training_consent" type="checkbox" value="yes">' in lung_gui.PAGE
    assert "checked" not in lung_gui.PAGE.split('name="training_consent"')[1].split(">")[0]


def test_upload_is_retained_only_with_consent(tmp_path, monkeypatch):
    monkeypatch.setattr(lung_gui, "TRAINING_DIR", tmp_path / "training")
    assert lung_gui.store_training_upload("a.png", b"img", 0.7, {}) is None
    assert not (tmp_path / "training").exists()

    ref = lung_gui.store_training_upload("a.png", b"img", 0.7, {"training_consent": "yes"})
    saved = {p.name for p in (tmp_path / "training").iterdir()}
    assert saved == {f"{ref}_a.png", f"{ref}.consent.json"}
    record = json.loads((tmp_path / "training" / f"{ref}.consent.json").read_text())
    assert record["consent_version"] == lung_gui.CONSENT_VERSION


def test_result_page_states_whether_image_was_retained():
    assert "with your consent" in lung_gui.render_result("a.png", EMPTY, "123_abcd")
    assert "discarded" in lung_gui.render_result("a.png", EMPTY)
