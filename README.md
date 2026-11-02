# Lung Cancer Imaging Analysis

Patient-matched lung cancer CT analysis on the TCIA collection
[CMB-LCA](https://www.cancerimagingarchive.net/collection/cmb-lca/). This project reuses the
structure of [AML-Imaging-Analysis](https://github.com/mfrendy-maker/AML-Imaging-Analysis)
(TCIA metadata snapshot, same-patient cohort, similarity, clustering, longitudinal CT
biomarkers, CT upload demo) and adds CT lesion detection, severity grading and
abnormality classification.

Research use only. Not for clinical diagnosis.

## Data citation and usage

Data come from The Cancer Imaging Archive (TCIA), collection CMB-LCA (Cancer Moonshot
Biobank - Lung Cancer). Cite the collection using the DOI on its
[collection page](https://www.cancerimagingarchive.net/collection/cmb-lca/) and follow the
[TCIA Data Usage Policy](https://www.cancerimagingarchive.net/data-usage-policies-and-restrictions/).
Raw DICOM is not stored in Git (`data/tcia_downloads/` is ignored).

## Quick start

```
python -m pip install -e .
lung-imaging --collection CMB-LCA --output-dir data      # TCIA metadata, similarity matrix
lung-lesion download --max-series 3                      # CT series from CMB-LCA via the NBIA API
lung-lesion convert <dicom_dir> data/ct.nii.gz           # DICOM -> NIfTI
python -m pip install -e ".[segmentation]"               # TotalSegmentator (lung masks)
lung-lesion analyse data/ct.nii.gz --out outputs         # lesions, severity, PNG overlays
lung-ct-demo                                             # browser CT upload demo (port 8003)
```

## Pipeline

1. Acquisition: TCIA NBIA API, CMB-LCA collection (`data_fetcher.py`).
2. Same-patient cohort, clinical outcomes, longitudinal change (`cohort.py`, `clinical.py`, `longitudinal.py`).
3. Similarity, clustering, biology report (`analysis.py`, `clustering.py`, `discovery.py`).
4. CT biomarker by response group (`ct_imaging.py`).
5. Lesion analysis: TotalSegmentator lung lobes, candidates (HU > -400 inside eroded lung, vessel-removing
   opening, connected components), per-lesion diameter, mean HU, sphericity, type
   (ground-glass / part-solid / solid / spiculated nodule / mass) and severity
   (low / moderate / high / critical, Lung-RADS-style size thresholds). Scan label: normal or abnormal.
   Annotated PNGs are written to `outputs/images/` (`lesions.py`, `segment.py`, `viz.py`).

For normal-lung controls, run step 5 on CTs with no lesions; TotalSegmentator is a
segmentation tool, not a normal-CT dataset.
