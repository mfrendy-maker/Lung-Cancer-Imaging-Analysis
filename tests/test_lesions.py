import numpy as np

from lung_imaging_analysis import lesions, segment


def _volume(radius_mm: float | None, hu_value: float = 40.0, size: int = 80):
    hu = np.full((size, size, size), -800.0, dtype=np.float32)
    lung = np.zeros_like(hu, dtype=bool)
    lung[5:-5, 5:-5, 5:-5] = True
    if radius_mm is not None:
        x, y, z = np.ogrid[:size, :size, :size]
        c = size // 2
        hu[(x - c) ** 2 + (y - c) ** 2 + (z - c) ** 2 <= radius_mm**2] = hu_value
    return hu, lung


def test_normal_volume_has_no_lesions():
    hu, lung = _volume(None)
    found, _ = lesions.detect_lesions(hu, lung, (1.0, 1.0, 1.0))
    assert found == []
    assert lesions.classify_scan(found)["label"] == "normal"


def test_solid_nodule_is_measured_and_graded():
    hu, lung = _volume(5.0)
    found, labels = lesions.detect_lesions(hu, lung, (1.0, 1.0, 1.0))
    assert len(found) == 1
    nodule = found[0]
    assert 8 <= nodule.diameter_mm <= 12
    assert nodule.kind == "solid nodule"
    assert nodule.severity == "high"
    assert lesions.classify_scan(found)["label"] == "abnormal"
    assert labels[40, 40, 40] == nodule.id


def test_ground_glass_is_classified_by_density():
    hu, lung = _volume(6.0, hu_value=-450.0)
    found, _ = lesions.detect_lesions(hu, lung, (1.0, 1.0, 1.0))
    assert found == [] or found[0].kind in {"ground-glass nodule", "part-solid nodule"}


def test_thin_vessel_is_not_a_lesion():
    hu, lung = _volume(None)
    hu[10:70, 40, 40] = 40.0
    found, _ = lesions.detect_lesions(hu, lung, (1.0, 1.0, 1.0))
    assert found == []


def test_threshold_lung_mask_keeps_lungs_that_run_to_the_scan_edges():
    hu = np.full((60, 60, 40), -1000.0, dtype=np.float32)
    hu[10:50, 10:50, :] = 40.0
    hu[20:40, 20:40, :] = -800.0
    mask = segment.threshold_lung_mask(hu)
    assert mask[30, 30, 0] and mask[30, 30, 39]
    assert not mask[0, 0, 20]


def test_threshold_lung_mask_finds_enclosed_air():
    hu = np.full((60, 60, 60), -1000.0, dtype=np.float32)
    hu[10:50, 10:50, 10:50] = 40.0
    hu[20:40, 20:40, 20:40] = -800.0
    mask = segment.threshold_lung_mask(hu)
    assert mask[30, 30, 30]
    assert not mask[0, 0, 0]
