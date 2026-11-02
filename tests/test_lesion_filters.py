import numpy as np

from lung_imaging_analysis import lesions

SP = (1.0, 1.0, 1.0)


def _lung(size: int = 80):
    hu = np.full((size, size, size), -800.0, dtype=np.float32)
    lung = np.zeros_like(hu, dtype=bool)
    lung[5:-5, 5:-5, 5:-5] = True
    return hu, lung


def test_contrast_dense_blob_is_not_a_nodule():
    hu, lung = _lung()
    x, y, z = np.ogrid[:80, :80, :80]
    hu[(x - 40) ** 2 + (y - 40) ** 2 + (z - 40) ** 2 <= 36] = 250.0
    found, _ = lesions.detect_lesions(hu, lung, SP)
    assert found == []


def test_thick_tube_is_rejected_as_a_vessel_but_a_round_nodule_is_kept():
    hu, lung = _lung()
    x, y, z = np.ogrid[:80, :80, :80]
    tube = ((y - 20) ** 2 + (z - 20) ** 2 <= 16) & (x > 10) & (x < 65)
    hu[tube] = 40.0
    nodule = (x - 40) ** 2 + (y - 55) ** 2 + (z - 55) ** 2 <= 36
    hu[nodule] = 40.0
    found, _ = lesions.detect_lesions(hu, lung, SP)
    assert len(found) == 1
    assert found[0].centroid_vox[1] > 45


def test_elongation_is_low_for_blobs_and_high_for_tubes():
    ball = np.zeros((30, 30, 30), bool)
    x, y, z = np.ogrid[:30, :30, :30]
    ball[(x - 15) ** 2 + (y - 15) ** 2 + (z - 15) ** 2 <= 64] = True
    tube = np.zeros((60, 12, 12), bool)
    tube[:, 3:9, 3:9] = True
    assert lesions._elongation(ball, SP) < 1.3
    assert lesions._elongation(tube, SP) > 3
