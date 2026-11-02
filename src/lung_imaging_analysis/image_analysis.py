"""Image-based lesion marking: lung mask, suspicious-spot detection, severity colouring and overlay rendering."""
from __future__ import annotations

import io
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi
from skimage.measure import label as sk_label
from skimage.measure import regionprops
from skimage.morphology import disk

from . import lesions, segment

SEVERITY_COLORS = {
    "low": (255, 214, 0),
    "moderate": (255, 140, 0),
    "high": (230, 30, 30),
    "critical": (210, 0, 210),
}
LEVELS = ["low", "moderate", "high", "critical"]
LEGEND = [
    ("low", "< 6 mm"),
    ("moderate", "6 - 8 mm"),
    ("high", "8 - 15 mm"),
    ("critical", ">= 15 mm / mass"),
]
# Display window assumed for 8-bit images: 0..255 maps to -1000..400 HU, so -400 HU is ~109.
AIR_THRESHOLD = 109
MAX_UPLOAD_BYTES = 300 * 1024 * 1024


@dataclass
class Finding:
    id: int
    x: int
    y: int
    bbox: tuple
    diameter_mm: float
    mean_hu: float
    circularity: float
    kind: str
    severity: str
    slice_index: int | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["bbox"] = list(self.bbox)
        return d


def _load_gray(data: bytes) -> tuple[np.ndarray, np.ndarray | None]:
    """Return (uint8 grayscale, mask of strongly coloured annotation pixels or None)."""
    with Image.open(io.BytesIO(data)) as img:
        if img.mode in ("I;16", "I", "F"):
            arr = np.asarray(img, dtype=np.float32)
            lo, hi = np.percentile(arr, [0.5, 99.5])
            return np.clip((arr - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8), None
        rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    saturation = (mx - mn) / np.maximum(mx, 1.0)
    coloured = ndi.binary_dilation((saturation > 0.35) & (mx > 80), iterations=3)
    gray = np.asarray(Image.fromarray(rgb.astype(np.uint8)).convert("L"))
    return gray, (coloured if coloured.any() else None)


def lung_mask_2d(v: np.ndarray, spacing: float) -> np.ndarray:
    air = v < AIR_THRESHOLD
    labels, n = ndi.label(air)
    if n == 0:
        return np.zeros_like(air)
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])))
    sizes = ndi.sum(air, labels, index=np.arange(1, n + 1))
    keep = [i + 1 for i in np.argsort(sizes)[::-1] if (i + 1) not in border and sizes[i] >= 0.01 * v.size][:2]
    mask = np.isin(labels, keep)
    if not mask.any():
        return mask
    # Closing keeps lesions that touch the pleura inside the lung mask.
    mask = ndi.binary_closing(mask, structure=disk(max(2, round(14.0 / spacing))))
    return ndi.binary_fill_holes(mask)


def detect_2d(v: np.ndarray, spacing: float, ignore: np.ndarray | None = None):
    """Return (lung_mask, [(mask, Finding)]) for one 8-bit lung-window slice."""
    lung = lung_mask_2d(v, spacing)
    candidates = ndi.binary_erosion(lung, structure=disk(2)) & (v > AIR_THRESHOLD)
    if ignore is not None:
        candidates &= ~ignore
    # Opening removes vessels and airway walls narrower than ~4 mm.
    candidates = ndi.binary_opening(candidates, structure=disk(max(1, round(2.0 / spacing))))
    labelled = sk_label(candidates)
    items = []
    for prop in regionprops(labelled):
        diameter = 2 * np.sqrt(prop.area * spacing**2 / np.pi)
        if diameter < 5.0 or prop.solidity < 0.75:
            continue
        mask = labelled == prop.label
        mean_hu = -1000 + float(v[mask].mean()) / 255 * 1400
        circularity = float(min(1.0, 4 * np.pi * prop.area / max(prop.perimeter, 1.0) ** 2))
        kind = lesions._kind(diameter, mean_hu, circularity)
        severity = lesions._severity(diameter, kind, circularity)
        r0, c0, r1, c1 = prop.bbox
        cy, cx = prop.centroid
        items.append((mask, Finding(0, int(cx), int(cy), (r0, c0, r1, c1), round(float(diameter), 1),
                                    round(mean_hu, 1), round(circularity, 2), kind, severity)))
    items.sort(key=lambda it: (-LEVELS.index(it[1].severity), -it[1].diameter_mm))
    for i, (_, f) in enumerate(items, 1):
        f.id = i
    return lung, items


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # older Pillow
        return ImageFont.load_default()


def render_overlay(gray: np.ndarray, items, caption: str = "") -> bytes:
    """Draw severity-coloured fills, contours, boxes and labels plus a legend panel; return PNG bytes."""
    h, w = gray.shape
    s = int(min(4, max(1, round(800 / max(h, w)))))
    base = np.repeat(np.repeat(gray, s, axis=0), s, axis=1)
    rgb = np.stack([base] * 3, axis=-1).astype(np.float32)
    for mask, f in items:
        m = np.repeat(np.repeat(mask, s, axis=0), s, axis=1)
        color = np.array(SEVERITY_COLORS[f.severity], dtype=np.float32)
        rgb[m] = rgb[m] * 0.55 + color * 0.45
        rgb[m & ~ndi.binary_erosion(m, iterations=max(1, s))] = color
    img = Image.fromarray(rgb.clip(0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(img)
    font = _font(max(13, 4 * s + 8))
    for _, f in items:
        r0, c0, r1, c1 = f.bbox
        pad = 6 * s
        box = [c0 * s - pad, r0 * s - pad, c1 * s + pad, r1 * s + pad]
        color = SEVERITY_COLORS[f.severity]
        draw.rectangle(box, outline=color, width=2)
        tag = f"#{f.id} {f.diameter_mm:.0f} mm {f.severity.upper()}"
        left, top, right, bottom = draw.textbbox((0, 0), tag, font=font)
        tw, th = right - left, bottom - top
        tx = int(max(0, min(box[0], img.width - tw - 8)))
        ty = box[1] - th - 10 if box[1] - th - 10 > 0 else box[3] + 2
        draw.rectangle([tx, ty, tx + tw + 8, ty + th + 8], fill=color)
        draw.text((tx + 4, ty + 2), tag, fill=(0, 0, 0), font=font)

    panel = 320
    canvas = Image.new("RGB", (img.width + panel, img.height), (255, 255, 255))
    canvas.paste(img, (0, 0))
    d = ImageDraw.Draw(canvas)
    big, small = _font(20), _font(15)
    x0, y = img.width + 18, 18
    d.text((x0, y), "Severity guide", fill=(0, 0, 0), font=big)
    y += 40
    for name, rule in LEGEND:
        d.rectangle([x0, y, x0 + 26, y + 26], fill=SEVERITY_COLORS[name])
        d.text((x0 + 38, y + 2), f"{name.capitalize()}  {rule}", fill=(0, 0, 0), font=small)
        y += 38
    d.text((x0, y + 4), "One level higher if irregular", fill=(51, 51, 51), font=small)
    d.text((x0, y + 24), "or part-solid", fill=(51, 51, 51), font=small)
    y += 64
    d.text((x0, y), f"Areas marked: {len(items)}", fill=(0, 0, 0), font=big)
    if caption:
        d.text((x0, y + 36), caption, fill=(51, 51, 51), font=small)
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def normal_reference_array(size: int = 384) -> np.ndarray:
    """Schematic normal axial chest CT in a lung window (not a real patient scan)."""
    rng = np.random.default_rng(7)
    y, x = np.mgrid[:size, :size].astype(np.float32)
    c = size / 2

    def ell(cx, cy, a, b):
        return ((x - cx) / a) ** 2 + ((y - cy) / b) ** 2 <= 1

    img = np.zeros((size, size), np.float32)
    img[ell(c, c * 1.02, size * 0.46, size * 0.36)] = 105          # subcutaneous fat
    img[ell(c, c * 1.02, size * 0.42, size * 0.32)] = 150          # chest wall muscle
    lungs = ell(c - size * 0.2, c * 0.98, size * 0.17, size * 0.25) | ell(c + size * 0.2, c * 0.98, size * 0.17, size * 0.25)
    img[lungs] = 38                                               # aerated lung
    img[ell(c, c * 1.0, size * 0.065, size * 0.2)] = 150          # mediastinum
    img[ell(c + size * 0.04, c * 0.9, size * 0.1, size * 0.1)] = 165    # heart
    img[ell(c + size * 0.045, c * 1.3, size * 0.03, size * 0.03)] = 185  # descending aorta
    img[ell(c, c * 1.36, size * 0.04, size * 0.04)] = 215         # vertebra
    for sx in (-1, 1):                                            # ribs
        for k in range(5):
            ang = np.deg2rad(-50 + k * 28)
            rx, ry = c + sx * size * 0.37 * np.cos(ang), c + size * 0.3 * np.sin(ang)
            img[ell(rx, ry, size * 0.022, size * 0.012)] = 205
    for sx in (-1, 1):                                            # branching vessels
        for _ in range(9):
            px, py = c + sx * size * 0.06, c * 0.95
            ang = rng.uniform(-1.2, 1.2) + (np.pi if sx < 0 else 0)
            for step in range(int(size * 0.13)):
                px += np.cos(ang) * 1.5
                py += np.sin(ang) * 1.5
                ang += rng.normal(0, 0.09)
                ix, iy = int(px), int(py)
                if 0 <= ix < size and 0 <= iy < size and lungs[iy, ix]:
                    width = 2 if step < size * 0.07 else 1
                    img[iy - width + 1:iy + width, ix - width + 1:ix + width] = 125
    img = ndi.gaussian_filter(img, 1.2)
    img[lungs] += rng.normal(0, 5, int(lungs.sum()))
    return np.clip(img, 0, 255).astype(np.uint8)


def normal_reference_png() -> bytes:
    """Labelled figure of a typical normal chest CT for comparison with the analysed image."""
    arr = normal_reference_array()
    s = 2
    base = Image.fromarray(np.repeat(np.repeat(arr, s, axis=0), s, axis=1)).convert("RGB")
    size = base.width
    top = 46
    canvas = Image.new("RGB", (size, size + top), (255, 255, 255))
    canvas.paste(base, (0, top))
    d = ImageDraw.Draw(canvas)
    title, small = _font(18), _font(14)
    d.text((10, 10), "Typical normal chest CT (schematic illustration)", fill=(0, 0, 0), font=title)
    labels = [("Right lung", 0.1, 0.5), ("Left lung", 0.7, 0.5), ("Heart", 0.47, 0.42), ("Aorta", 0.58, 0.66), ("Spine", 0.37, 0.70)]
    for text, fx, fy in labels:
        px, py = int(fx * size), int(fy * size) + top
        box = d.textbbox((px, py), text, font=small)
        d.rectangle([box[0] - 3, box[1] - 2, box[2] + 3, box[3] + 2], fill=(255, 255, 255))
        d.text((px, py), text, fill=(0, 0, 0), font=small)
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def _summary(findings: list[Finding]) -> dict:
    if not findings:
        return {"label": "no suspicious regions found", "severity": "none", "dominant_finding": None}
    worst = max(findings, key=lambda f: (LEVELS.index(f.severity), f.diameter_mm))
    return {"label": "suspicious regions found", "severity": worst.severity, "dominant_finding": worst.kind}


def _analyse_2d(data: bytes, spacing: float) -> dict:
    gray, coloured = _load_gray(data)
    _, items = detect_2d(gray, spacing, ignore=coloured)
    findings = [f for _, f in items]
    png = render_overlay(gray, items, f"Assumed pixel size {spacing} mm")
    return {**_summary(findings), "findings": [f.to_dict() for f in findings], "images": [png],
            "notes": [f"Sizes assume {spacing} mm per pixel and a lung window of -1000 to 400 HU; "
                      "set the pixel size for accurate measurements."]}


def _analyse_nifti(data: bytes, filename: str, max_images: int = 4) -> dict:
    import nibabel as nib

    suffix = ".nii.gz" if filename.lower().endswith(".gz") else ".nii"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"scan{suffix}"
        path.write_bytes(data)
        img = nib.load(str(path))
        hu = np.asarray(img.dataobj, dtype=np.float32)
        spacing = tuple(float(z) for z in img.header.get_zooms()[:3])
    if hu.ndim != 3:
        raise ValueError("Expected a 3D CT volume")
    lung = segment.threshold_lung_mask(hu)
    found, labels = lesions.detect_lesions(hu, lung, spacing)
    found.sort(key=lambda l: (-LEVELS.index(l.severity), -l.diameter_mm))

    findings, images, drawn_slices = [], [], set()
    for les in found:
        z = les.centroid_vox[2]
        mask3 = labels[:, :, z] == les.id
        if not mask3.any():
            continue
        rows, cols = np.where(mask3.T[::-1])
        f = Finding(les.id, int(cols.mean()), int(rows.mean()), (int(rows.min()), int(cols.min()), int(rows.max()), int(cols.max())),
                    les.diameter_mm, les.mean_hu, les.sphericity, les.kind, les.severity, z)
        findings.append(f)
        if z in drawn_slices or len(images) >= max_images:
            continue
        drawn_slices.add(z)
        slice_hu = hu[:, :, z].T[::-1]
        gray = np.clip((slice_hu + 1000) / 1400 * 255, 0, 255).astype(np.uint8)
        on_slice = []
        for other in found:
            m = (labels[:, :, z] == other.id).T[::-1]
            if m.any():
                r, c = np.where(m)
                of = Finding(other.id, int(c.mean()), int(r.mean()), (int(r.min()), int(c.min()), int(r.max()), int(c.max())),
                             other.diameter_mm, other.mean_hu, other.sphericity, other.kind, other.severity, z)
                on_slice.append((m, of))
        images.append(render_overlay(gray, on_slice, f"Axial slice {z}"))
    if not images:
        z = int(np.argmax(lung.sum(axis=(0, 1)))) if lung.any() else hu.shape[2] // 2
        gray = np.clip((hu[:, :, z].T[::-1] + 1000) / 1400 * 255, 0, 255).astype(np.uint8)
        images.append(render_overlay(gray, [], f"Axial slice {z}"))
    return {**_summary(findings), "findings": [f.to_dict() for f in findings], "images": images,
            "notes": [f"3D volume analysed with the threshold lung mask; voxel size {spacing[0]:.2f} x {spacing[1]:.2f} x {spacing[2]:.2f} mm."]}


def analyse_upload(filename: str, data: bytes, spacing_mm: float = 0.7) -> dict:
    """Analyse an uploaded CT image (PNG/JPG/TIFF/BMP) or NIfTI volume."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("File is too large")
    if not 0.05 <= spacing_mm <= 5.0:
        raise ValueError("Pixel size must be between 0.05 and 5 mm")
    name = filename.lower()
    if name.endswith((".nii", ".nii.gz")):
        return _analyse_nifti(data, filename)
    try:
        return _analyse_2d(data, spacing_mm)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError(f"Could not read the image: {exc}") from exc
