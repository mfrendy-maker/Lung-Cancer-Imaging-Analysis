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
