import pandas as pd

from lung_imaging_analysis.analysis import build_patient_similarity_matrix
from lung_imaging_analysis.data_fetcher import fetch_collection_snapshot


def test_build_patient_similarity_matrix():
    df = pd.DataFrame(
        {
            "patient_id": ["P1", "P2", "P3"],
            "modality": ["CT", "MR", "CT"],
            "study_count": [3, 2, 3],
            "series_count": [10, 8, 11],
            "image_count": [450, 520, 460],
        }
    )

    similarity = build_patient_similarity_matrix(df)

    assert similarity.shape == (3, 3)
    assert similarity.iloc[0, 0] == 1.0
    assert similarity.iloc[0, 1] >= 0.0
    assert similarity.iloc[0, 1] <= 1.0


def test_fetch_collection_snapshot_returns_expected_fields(monkeypatch):
    def fake_fetch(url):
        if "getPatient" in url:
            return [{"PatientId": "P1"}, {"PatientId": "P2"}]
        return [
            {"PatientID": "P1", "StudyInstanceUID": "s1", "Modality": "CT", "ImageCount": 100},
            {"PatientID": "P2", "StudyInstanceUID": "s2", "Modality": "CT", "ImageCount": 120},
        ]

    monkeypatch.setattr("lung_imaging_analysis.data_fetcher._fetch_json", fake_fetch)
    snapshot = fetch_collection_snapshot(collection_name="CMB-LCA")

    assert "collection" in snapshot
    assert "patients" in snapshot
    assert snapshot["collection"] == "CMB-LCA"
