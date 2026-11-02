import re

from lung_imaging_analysis import clinical_info, image_analysis, lung_gui

EMPTY = {"label": "x", "severity": "none", "dominant_finding": None, "findings": [], "images": [], "notes": []}
CRITICAL = {
    "label": "x", "severity": "critical", "dominant_finding": "mass", "images": [], "notes": [],
    "findings": [{"id": 1, "kind": "mass", "severity": "critical", "diameter_mm": 35.0, "mean_hu": 40.0,
                  "x": 1, "y": 2, "slice_index": None}],
}


def test_normal_reference_has_nothing_to_mark():
    arr = image_analysis.normal_reference_array()
    _, items = image_analysis.detect_2d(arr, 0.9)
    assert items == []
    assert image_analysis.normal_reference_png().startswith(b"\x89PNG")


def test_guidance_scales_with_severity_and_has_every_section():
    normal = clinical_info.guidance_for(EMPTY)
    severe = clinical_info.guidance_for(CRITICAL)
    assert any("urgent" in s.lower() for s in severe["next_steps"])
    assert not any("urgent" in s.lower() for s in normal["next_steps"])
    assert any("lung cancer" in name.lower() for name, _ in severe["causes"])
    for key in ("causes", "next_steps", "medications", "personal_care", "urgent"):
        assert severe[key] and normal[key]


def test_guidance_never_gives_doses():
    text = " ".join(clinical_info.MEDICATION_NOTES + clinical_info.PERSONAL_CARE)
    assert not re.search(r"\b\d+\s?(mg|mcg|ml|tablets?)\b", text, re.I)
    assert "not a prescription" in lung_gui.render_result("a.png", CRITICAL)


def test_result_page_shows_guidance_and_normal_figure():
    page = lung_gui.render_result("a.png", CRITICAL)
    for heading in ("Possible explanations", "Suggested next steps", "About medicines",
                    "Personal care and recommended activity", "Seek urgent medical care", "typical normal chest CT"):
        assert heading in page
