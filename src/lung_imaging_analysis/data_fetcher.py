from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

TCIA_BASE_URL = "https://services.cancerimagingarchive.net/nbia-api/services/v1"


def _fetch_json(url: str) -> Any:
    response = requests.get(url, timeout=60, headers={"User-Agent": "Lung-Cancer-Imaging-Analysis/0.1"})
    response.raise_for_status()
    return response.json()


def _patient_series_summary(series_records: list[dict]) -> list[dict]:
    by_patient: dict[str, list[dict]] = {}
    for record in series_records:
        patient_id = record.get("PatientID") or record.get("patient_id")
        if patient_id is None:
            continue
        by_patient.setdefault(patient_id, []).append(record)

    summary_rows: list[dict] = []
    for patient_id, records in sorted(by_patient.items()):
        study_ids = {record.get("StudyInstanceUID") for record in records if record.get("StudyInstanceUID")}
        modality_counts: dict[str, int] = {}
        for record in records:
            modality = record.get("Modality") or "Unknown"
            modality_counts[modality] = modality_counts.get(modality, 0) + 1

        summary_rows.append(
            {
                "patient_id": patient_id,
                "study_count": len(study_ids),
                "series_count": len(records),
                "modality": sorted(modality_counts, key=modality_counts.get, reverse=True)[0] if modality_counts else "Unknown",
                "modalities": modality_counts,
                "image_count": sum(int(record.get("ImageCount") or 0) for record in records),
            }
        )
    return summary_rows


def fetch_collection_snapshot(collection_name: str = "CMB-LCA", limit_patients: int | None = None) -> dict[str, Any]:
    patient_url = f"{TCIA_BASE_URL}/getPatient?Collection={collection_name}"
    patient_records = _fetch_json(patient_url)
    if limit_patients is not None:
        patient_records = patient_records[:limit_patients]

    series_url = f"{TCIA_BASE_URL}/getSeries?Collection={collection_name}"
    series_records = _fetch_json(series_url)

    patient_ids = {record.get("PatientId") or record.get("PatientID") for record in patient_records if record.get("PatientId") or record.get("PatientID")}
    filtered_series = [record for record in series_records if (record.get("PatientID") or record.get("PatientId")) in patient_ids]
    patient_summary = _patient_series_summary(filtered_series)

    snapshot = {
        "collection": collection_name,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_count": len(patient_records),
        "patients": patient_summary,
        "patient_ids": sorted(patient_ids),
    }
    return snapshot


def persist_collection_snapshot(snapshot: dict[str, Any], output_path: str | Path = "data/collection_snapshot.json") -> Path:
    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as outfile:
        json.dump(snapshot, outfile, indent=2)
    return target_path


def _pick_series(records: list[dict], max_series: int) -> list[dict]:
    # Chest-sized volumes (100-600 slices), closest to 250 first; avoids scouts and huge whole-body series.
    sized = [r for r in records if 100 <= int(r.get("ImageCount") or 0) <= 600]
    return sorted(sized or records, key=lambda r: abs(int(r.get("ImageCount") or 0) - 250))[:max_series]


def download_collection_ct(collection_name: str = "CMB-LCA", output_dir: str | Path = "data/tcia_downloads", max_series: int = 5) -> list[Path]:
    """Download CT series from a public TCIA collection via the NBIA API, streaming each zip to disk."""
    import zipfile

    series_records = _pick_series(_fetch_json(f"{TCIA_BASE_URL}/getSeries?Collection={collection_name}&Modality=CT"), max_series)
    out_dirs: list[Path] = []
    for record in series_records:
        uid = record["SeriesInstanceUID"]
        target = Path(output_dir) / record.get("PatientID", "unknown") / uid
        target.mkdir(parents=True, exist_ok=True)
        zip_path = target / "series.zip"
        print(f"Downloading {record.get('PatientID')} {uid} ({record.get('ImageCount')} images)", flush=True)
        with requests.get(f"{TCIA_BASE_URL}/getImage", params={"SeriesInstanceUID": uid}, stream=True, timeout=(30, 120)) as response:
            response.raise_for_status()
            done = 0
            next_report = 10 << 20
            with zip_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    handle.write(chunk)
                    done += len(chunk)
                    if done >= next_report:
                        print(f"  {done >> 20} MB", flush=True)
                        next_report += 10 << 20
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(target)
        zip_path.unlink()
        out_dirs.append(target)
    return out_dirs

def dicom_to_nifti(dicom_dir: str | Path, out_file: str | Path) -> str:
    import SimpleITK as sitk

    reader = sitk.ImageSeriesReader()
    files = reader.GetGDCMSeriesFileNames(str(dicom_dir))
    if not files:
        raise FileNotFoundError(f"No DICOM series in {dicom_dir}")
    reader.SetFileNames(files)
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)
    sitk.WriteImage(reader.Execute(), str(out_file))
    return str(out_file)
