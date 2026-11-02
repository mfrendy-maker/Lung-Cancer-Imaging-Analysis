import argparse
import json
from pathlib import Path

import nibabel as nib
import numpy as np

from . import data_fetcher, lesions, segment, viz


def analyse(ct_nifti: str, work_dir: str, fast: bool = True, backend: str = "threshold") -> dict:
    img = nib.load(ct_nifti)
    hu = np.asarray(img.dataobj, dtype=np.float32)
    spacing = img.header.get_zooms()[:3]
    if backend == "totalsegmentator":
        lung = segment.segment_lungs(ct_nifti, work_dir, fast=fast)
    else:
        lung = segment.threshold_lung_mask(hu)
    found, labels = lesions.detect_lesions(hu, lung, spacing)
    result = lesions.classify_scan(found)
    result["images"] = viz.save_overlays(hu, lung, labels, found, str(Path(work_dir) / "images"), result["label"])
    return result


def compare(cancer_dir: str, normal_dir: str, out_dir: str, backend: str = "threshold"):
    import pandas as pd

    rows = []
    for group, folder in ("cancer", cancer_dir), ("normal", normal_dir):
        for f in sorted(Path(folder).glob("*.nii*")):
            out = Path(out_dir) / group / f.name.split(".")[0]
            out.mkdir(parents=True, exist_ok=True)
            res = analyse(str(f), str(out), backend=backend)
            sizes = [l["diameter_mm"] for l in res["lesions"]]
            rows.append({"group": group, "scan": f.name, "label": res["label"], "severity": res["severity"],
                         "lesion_count": len(sizes), "max_diameter_mm": max(sizes, default=0.0)})
    df = pd.DataFrame(rows)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    df.to_csv(Path(out_dir) / "comparison.csv", index=False)
    print(df.groupby("group")[["lesion_count", "max_diameter_mm"]].agg(["mean", "max"]))
    return df


def main():
    p = argparse.ArgumentParser(prog="lung-lesion")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="download CMB-LCA CT series from TCIA")
    d.add_argument("--out", default="data/tcia_downloads")
    d.add_argument("--max-series", type=int, default=5)

    c = sub.add_parser("convert", help="DICOM series folder -> NIfTI")
    c.add_argument("dicom_dir")
    c.add_argument("out_file")

    a = sub.add_parser("analyse", help="segment lungs, detect lesions, grade and classify")
    a.add_argument("ct_nifti")
    a.add_argument("--out", default="outputs")
    a.add_argument("--full", action="store_true", help="full-resolution TotalSegmentator (slower)")
    a.add_argument("--backend", choices=["threshold", "totalsegmentator"], default="threshold")

    r = sub.add_parser("run", help="download, convert and analyse CMB-LCA series in one step")
    r.add_argument("--out", default="outputs")
    r.add_argument("--max-series", type=int, default=1)
    r.add_argument("--backend", choices=["threshold", "totalsegmentator"], default="threshold")

    m = sub.add_parser("compare", help="analyse cancer and normal NIfTI folders and write a summary CSV")
    m.add_argument("--cancer", required=True, help="folder of cancer CT .nii.gz")
    m.add_argument("--normal", required=True, help="folder of normal CT .nii.gz")
    m.add_argument("--out", default="outputs/compare")
    m.add_argument("--backend", choices=["threshold", "totalsegmentator"], default="threshold")

    args = p.parse_args()
    if args.cmd == "download":
        data_fetcher.download_collection_ct("CMB-LCA", args.out, args.max_series)
    elif args.cmd == "convert":
        print(data_fetcher.dicom_to_nifti(args.dicom_dir, args.out_file))
    elif args.cmd == "run":
        for series_dir in data_fetcher.download_collection_ct("CMB-LCA", "data/tcia_downloads", args.max_series):
            nifti = data_fetcher.dicom_to_nifti(series_dir, Path("data/nifti") / f"{series_dir.parent.name}.nii.gz")
            out = Path(args.out) / series_dir.parent.name
            out.mkdir(parents=True, exist_ok=True)
            result = analyse(nifti, str(out), backend=args.backend)
            (out / "report.json").write_text(json.dumps(result, indent=2))
            print(series_dir.parent.name, result["label"], result["severity"])
    elif args.cmd == "compare":
        compare(args.cancer, args.normal, args.out, args.backend)
    else:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        result = analyse(args.ct_nifti, str(out), fast=not args.full, backend=args.backend)
        (out / "report.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
