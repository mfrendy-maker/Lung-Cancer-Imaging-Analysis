"""Lesion detection, measurement, severity grading and type classification."""
from dataclasses import asdict, dataclass

import numpy as np
from scipy import ndimage as ndi
from skimage.measure import marching_cubes, mesh_surface_area


@dataclass
class Lesion:
    id: int
    centroid_vox: tuple
    volume_mm3: float
    diameter_mm: float
    mean_hu: float
    sphericity: float
    kind: str
    severity: str


def _kind(d: float, mean_hu: float, sph: float) -> str:
    if mean_hu < -300:
        return "ground-glass nodule"
    if mean_hu < -100:
        return "part-solid nodule"
    if d >= 30:
        return "mass (spiculated/irregular)" if sph < 0.6 else "mass"
    return "spiculated solid nodule" if sph < 0.6 else "solid nodule"


def _severity(d: float, kind: str, sph: float) -> str:
    """Lung-RADS-inspired size grading; irregular shape or part-solid raises a level."""
    levels = ["low", "moderate", "high", "critical"]
    lvl = 0 if d < 6 else 1 if d < 8 else 2 if d < 15 else 3 if d < 30 else 3
    if d >= 30:
        lvl = 3
    if (sph < 0.6 or kind == "part-solid nodule") and lvl < 3:
        lvl += 1
    return levels[lvl]


def _sphericity(mask: np.ndarray, spacing) -> float:
    vol = mask.sum() * float(np.prod(spacing))
    if mask.sum() < 20:
        return 1.0
    try:
        verts, faces, _, _ = marching_cubes(mask.astype(np.uint8), 0.5, spacing=spacing)
        area = mesh_surface_area(verts, faces)
        return float(min(1.0, (np.pi ** (1 / 3)) * (6 * vol) ** (2 / 3) / area))
    except (ValueError, RuntimeError):
        return 1.0


def detect_lesions(hu: np.ndarray, lung: np.ndarray, spacing, min_diam_mm: float = 4.0):
    """hu: CT array (HU), lung: bool mask, spacing: voxel size (mm) in array axis order."""
    inner = ndi.binary_erosion(lung, iterations=2)
    candidates = inner & (hu > -400)
    # Opening removes thin vessels/airway walls, keeping compact lesions.
    candidates = ndi.binary_opening(candidates, structure=ndi.generate_binary_structure(3, 1), iterations=2)
    labels, n = ndi.label(candidates)
    voxel_vol = float(np.prod(spacing))
    lesions = []
    kept = np.zeros_like(labels)
    for i in range(1, n + 1):
        m = labels == i
        vol = m.sum() * voxel_vol
        d = 2 * (3 * vol / (4 * np.pi)) ** (1 / 3)
        if d < min_diam_mm:
            continue
        kept[m] = i
        mean_hu = float(hu[m].mean())
        sph = _sphericity(m, spacing)
        kind = _kind(d, mean_hu, sph)
        c = tuple(int(x) for x in ndi.center_of_mass(m))
        lesions.append(Lesion(i, c, round(vol, 1), round(d, 1), round(mean_hu, 1), round(sph, 2), kind, _severity(d, kind, sph)))
    return lesions, kept


def classify_scan(lesions) -> dict:
    if not lesions:
        return {"label": "normal", "severity": "none", "lesions": []}
    order = ["low", "moderate", "high", "critical"]
    worst = max(lesions, key=lambda l: order.index(l.severity))
    return {
        "label": "abnormal",
        "severity": worst.severity,
        "dominant_finding": worst.kind,
        "lesions": [asdict(l) for l in lesions],
    }
