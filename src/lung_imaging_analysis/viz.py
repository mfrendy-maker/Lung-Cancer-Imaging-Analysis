"""Annotated image output: axial slice per lesion with lung outline and lesion mask."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

COLORS = {"low": "yellow", "moderate": "orange", "high": "red", "critical": "magenta"}


def _window(sl, lo=-1000, hi=400):
    return np.clip((sl - lo) / (hi - lo), 0, 1)


def save_overlays(hu, lung, labels, found, out_dir: str, label: str) -> list[str]:
    """labels: lesion label volume matching Lesion.id. Returns written PNG paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []

    if not found:
        z = int(np.argmax(lung.sum(axis=(0, 1))))
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.imshow(_window(hu[:, :, z]).T, cmap="gray", origin="lower")
        ax.contour(lung[:, :, z].T, levels=[0.5], colors="cyan", linewidths=0.8)
        ax.set_title(f"{label.upper()} - no lesions detected")
        ax.axis("off")
        p = out / "overview.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return [str(p)]

    for les in found:
        z = les.centroid_vox[2]
        fig, axes = plt.subplots(1, 2, figsize=(11, 5.5))
        base = _window(hu[:, :, z]).T
        for ax in axes:
            ax.imshow(base, cmap="gray", origin="lower")
            ax.contour(lung[:, :, z].T, levels=[0.5], colors="cyan", linewidths=0.6)
            ax.axis("off")
        m = (labels[:, :, z] == les.id).T
        color = COLORS[les.severity]
        axes[1].contour(m, levels=[0.5], colors=color, linewidths=1.5)
        cx, cy = les.centroid_vox[0], les.centroid_vox[1]
        r = 40
        axes[1].set_xlim(cx - r, cx + r)
        axes[1].set_ylim(cy - r, cy + r)
        axes[0].plot(cx, cy, "o", mfc="none", mec=color, ms=18)
        axes[0].set_title("Axial slice (lung outline in cyan)")
        axes[1].set_title(f"{les.kind} | {les.diameter_mm} mm | {les.severity.upper()}")
        fig.suptitle(f"Lesion {les.id}: mean {les.mean_hu} HU, sphericity {les.sphericity}")
        p = out / f"lesion_{les.id:02d}.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        paths.append(str(p))
    return paths
