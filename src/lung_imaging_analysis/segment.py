"""Lung segmentation with TotalSegmentator."""
from pathlib import Path

import nibabel as nib
import numpy as np

LOBES = [
    "lung_upper_lobe_left",
    "lung_lower_lobe_left",
    "lung_upper_lobe_right",
    "lung_middle_lobe_right",
    "lung_lower_lobe_right",
]


def threshold_lung_mask(hu: np.ndarray) -> np.ndarray:
    """Torch-free lung mask: air-like voxels not connected to the outside, two largest components."""
    from scipy import ndimage as ndi

    air = hu < -320
    labels, n = ndi.label(air)
    if n == 0:
        return np.zeros_like(air)
    border = set(np.unique(np.concatenate([
        labels[0].ravel(), labels[-1].ravel(), labels[:, 0].ravel(), labels[:, -1].ravel(),
        labels[:, :, 0].ravel(), labels[:, :, -1].ravel(),
    ])))
    sizes = ndi.sum(air, labels, index=range(1, n + 1))
    keep = [i + 1 for i in np.argsort(sizes)[::-1] if (i + 1) not in border][:2]
    mask = np.isin(labels, keep)
    # Close per slice so juxtapleural lesions stay inside the mask.
    for z in range(mask.shape[2]):
        if mask[:, :, z].any():
            mask[:, :, z] = ndi.binary_fill_holes(ndi.binary_closing(mask[:, :, z], iterations=8))
    return mask


def segment_lungs(ct_nifti: str, out_dir: str, fast: bool = True) -> np.ndarray:
    """Run TotalSegmentator and return a boolean lung mask aligned with the CT."""
    from totalsegmentator.python_api import totalsegmentator

    totalsegmentator(ct_nifti, out_dir, roi_subset=LOBES, fast=fast)
    mask = None
    for name in LOBES:
        f = Path(out_dir) / f"{name}.nii.gz"
        if f.exists():
            m = nib.load(str(f)).get_fdata() > 0
            mask = m if mask is None else (mask | m)
    if mask is None:
        raise RuntimeError("TotalSegmentator produced no lung masks")
    return mask
