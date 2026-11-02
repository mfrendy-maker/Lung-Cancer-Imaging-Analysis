# Lung Cancer Imaging Analysis

Patient-matched lung cancer CT analysis on the TCIA collection
[CMB-LCA](https://www.cancerimagingarchive.net/collection/cmb-lca/). This project reuses the
structure of [AML-Imaging-Analysis](https://github.com/mfrendy-maker/AML-Imaging-Analysis)
(TCIA metadata snapshot, same-patient cohort, similarity, clustering, longitudinal CT
biomarkers, CT upload demo) and adds CT lesion detection, severity grading and
abnormality classification.

Research use only. Not for clinical diagnosis. Feel free to use!

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
lung-lesion run --max-series 1                           # download + convert + analyse in one step
lung-lesion download --max-series 3                      # CT series from CMB-LCA via the NBIA API
lung-lesion convert <dicom_dir> data/ct.nii.gz           # DICOM -> NIfTI
lung-lesion analyse data/ct.nii.gz --out outputs         # lesions, severity, PNG overlays (threshold lung mask)
python -m pip install -e ".[segmentation]"               # optional: TotalSegmentator
lung-lesion analyse data/ct.nii.gz --backend totalsegmentator
lung-lesion compare --cancer cancer_cts --normal normal_cts   # cancer vs normal summary CSV
lung-ct-demo                                             # browser CT upload demo (port 8003)
```

Tests: `python -m pytest` (offline; TCIA calls are mocked).

## Pipeline

1. Acquisition: TCIA NBIA API, CMB-LCA collection (`data_fetcher.py`).
2. Same-patient cohort, clinical outcomes, longitudinal change (`cohort.py`, `clinical.py`, `longitudinal.py`).
3. Similarity, clustering, biology report (`analysis.py`, `clustering.py`, `discovery.py`).
4. CT biomarker by response group (`ct_imaging.py`).
5. Lesion analysis: lung mask (threshold-based by default, TotalSegmentator lobes optional), candidates
   (HU > -400 inside the eroded lung, spherical opening to remove vessels, connected components), per-lesion diameter, mean HU, sphericity, type
   (ground-glass / part-solid / solid / spiculated nodule / mass) and severity
   (low / moderate / high / critical, Lung-RADS-style size thresholds). Scan label: normal or abnormal.
   Annotated PNGs are written to `outputs/images/` (`lesions.py`, `segment.py`, `viz.py`).

For normal-lung controls, run `lung-lesion compare` with a folder of CTs that have no lesions;
TotalSegmentator is a segmentation tool, not a normal-CT dataset.

## Example output

## Lesion analysis GUI

```
lung-gui          # http://127.0.0.1:8005/  (set GUI_PORT to change)
```

Upload a lung CT slice (PNG, JPG, TIFF, BMP) or a NIfTI volume. Suspected lesions are filled and outlined
in a severity colour (yellow low, orange moderate, red high, magenta critical), boxed, and labelled with
size and severity, with a legend and a findings table. For 2D images, enter the pixel size in mm so sizes
are meaningful. Images are processed in memory and not stored. Heuristic and unvalidated; not for diagnosis.

![GUI output](docs/gui_sample.png)

(Synthetic chest drawing, not patient data.)

### Consent for tool development

The upload form has an optional consent checkbox, unchecked by default. Without it the image is analysed in memory and
discarded. If ticked, the uploader confirms they are authorised to share the image and have removed identifying
information, and agrees that it may be retained and used to develop, test and improve this tool's analysis module.
The file is saved under `data/training_uploads/` (ignored by Git) with a `.consent.json` record (consent text, version,
timestamp). The tool does not de-identify images or DICOM/NIfTI headers. Consent can be withdrawn by asking the
operator to delete the file and its record.

## Example output

Synthetic volume (a 14 mm solid sphere in simulated lung), not patient data:

![Sample lesion overlay](docs/sample_overlay.png)

### Accessing the GUI

`http://127.0.0.1:8005/` is a loopback address, so it only works on the machine running the server.

| Who | How |
|---|---|
| Same computer | Open `http://127.0.0.1:8005/` in a browser. |
| Same network | The server currently binds to `127.0.0.1` only. Change `HOST` in `lung_gui.py` to `0.0.0.0`, allow port 8005 in the firewall, then use `http://<server-ip>:8005/`. |
| Internet | Use a tunnel (temporary URL, only while the machine is on) or deploy to a server. Add access control and a smaller upload limit first, because anyone with the link could upload images. |

Browser or Python both work, since the server speaks plain HTTP. From Python:

```python
import requests

with open("chest.png", "rb") as f:
    r = requests.post(
        "http://127.0.0.1:8005/analyse",   # use the LAN or public address for remote users
        files={"image": ("chest.png", f, "image/png")},
        data={"spacing": "0.7"},           # add "training_consent": "yes" only with the uploader's consent
        timeout=120,
    )
open("result.html", "w", encoding="utf-8").write(r.text)
```

The response is an HTML page, not JSON. A JSON API endpoint is not implemented yet.

## Limitations

- Detection and severity use fixed thresholds, not a trained model. CMB-LCA has little voxel-level
  tumour annotation, so sensitivity and false-positive rates are not measured. A labelled collection
  (for example LIDC-IDRI nodule annotations or NSCLC-Radiomics contours) is needed to validate or
  train a classifier.
- The browser upload demo still reports 2D image statistics only; it does not run the 3D lesion pipeline.

### Result guidance

Result pages include general educational information: possible explanations for the marked appearance, suggested next steps scaled to severity, notes on how medicines are chosen (no doses, not a prescription), personal care and activity advice, warning signs for urgent care, and a schematic normal chest CT for comparison. This content is generic (see `clinical_info.py`), is not personalised, and is not medical advice.
