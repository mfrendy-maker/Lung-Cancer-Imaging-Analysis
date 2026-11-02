"""Browser GUI: upload a lung CT image, mark suspected lesions with severity colours."""
from __future__ import annotations

import base64
import html
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import image_analysis
from .ct_upload_demo import _parse_multipart_form, _safe_name

HOST = "127.0.0.1"
PORT = int(os.environ.get("GUI_PORT", "8005"))
TRAINING_DIR = Path(__file__).resolve().parents[2] / "data" / "training_uploads"
CONSENT_VERSION = "2026-11-v1"
CONSENT_TEXT = (
    "I consent to my uploaded CT image being retained and used to develop, test and improve the analysis "
    "module of this tool (for example evaluating or training lesion-detection models). I confirm I am "
    "authorised to share this image and have removed patient-identifying information (name, ID, dates, DICOM metadata)."
)

CSS = """
body{font-family:Segoe UI,Arial,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:24px}
.wrap{max-width:1250px;margin:0 auto}
h1{margin:0 0 4px}.sub{color:#94a3b8;margin-bottom:20px}
.card{background:#111c33;border:1px solid #1e2d4d;border-radius:14px;padding:20px;margin-top:18px}
.drop{border:2px dashed #3b5b99;border-radius:12px;padding:36px;text-align:center;cursor:pointer;background:#0d162b}
.drop.over{background:#16254a}
label{display:block;margin:14px 0 6px;color:#94a3b8;font-size:13px;text-transform:uppercase;letter-spacing:.06em}
input[type=number]{background:#0d162b;color:#e2e8f0;border:1px solid #2a3f6b;border-radius:8px;padding:8px;width:120px}
button{background:#2563eb;color:#fff;border:0;border-radius:8px;padding:12px 22px;font-size:16px;cursor:pointer;margin-top:18px}
button:disabled{background:#475569}
img.result{max-width:100%;border-radius:10px;border:1px solid #1e2d4d;margin-top:10px}
table{border-collapse:collapse;width:100%;margin-top:10px}
th,td{padding:8px 10px;border-bottom:1px solid #1e2d4d;text-align:left;font-size:14px}
th{color:#94a3b8;font-weight:600}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;color:#000;font-weight:700;font-size:12px}
.warn{background:#2a1d10;border:1px solid #7c4a12;color:#fbd38d;border-radius:10px;padding:12px;margin-top:18px;font-size:14px}
a{color:#7dd3fc}
.consent{background:#0d162b;border:1px solid #2a3f6b;border-radius:10px;padding:14px;margin-top:18px;font-size:14px}
.consent p{color:#94a3b8;margin:10px 0 0;font-size:13px}
label.chk{display:flex;gap:10px;align-items:flex-start;margin:0;color:#e2e8f0;text-transform:none;letter-spacing:0;font-size:14px}
label.chk input{margin-top:4px}
"""

PAGE = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Lung CT Lesion Analysis</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>Lung CT Lesion Analysis</h1>
<div class="sub">Upload a lung CT image. Suspected lesions are marked and coloured by severity.</div>
<div class="card"><form id="f" action="/analyse" method="post" enctype="multipart/form-data">
<div class="drop" id="drop"><div id="msg">Drop a CT image here or click to choose<br>
<small>PNG, JPG, TIFF, BMP (single axial slice) or NIfTI (.nii, .nii.gz volume)</small></div>
<input id="file" name="image" type="file" accept=".png,.jpg,.jpeg,.tif,.tiff,.bmp,.nii,.nii.gz" hidden required></div>
<label for="spacing">Pixel size (mm per pixel, 2D images only)</label>
<input id="spacing" name="spacing" type="number" step="0.01" min="0.05" max="5" value="0.7">
<div class="consent"><label class="chk"><input name="training_consent" type="checkbox" value="yes"> <span>{html.escape(CONSENT_TEXT)}</span></label>
<p>Optional and off by default. Without consent your image is analysed in memory and discarded right after the result is shown.
With consent it is saved on the machine running this tool, together with a record of this consent, and may be used only to develop the tool.
Contact the tool operator to withdraw consent and have the image deleted. Do not tick this for images that still contain identifying information.</p></div>
<div><button id="go" type="submit">Analyse</button></div></form></div>
<div class="warn">Research tool using simple image-processing heuristics. It is not validated, can miss lesions or
mark normal structures, and must not be used for diagnosis.</div>
<script>
const drop=document.getElementById('drop'),file=document.getElementById('file'),msg=document.getElementById('msg');
drop.onclick=()=>file.click();
file.onchange=()=>{{if(file.files[0])msg.textContent=file.files[0].name}};
drop.ondragover=e=>{{e.preventDefault();drop.classList.add('over')}};
drop.ondragleave=()=>drop.classList.remove('over');
drop.ondrop=e=>{{e.preventDefault();drop.classList.remove('over');file.files=e.dataTransfer.files;file.onchange()}};
document.getElementById('f').onsubmit=()=>{{const b=document.getElementById('go');b.disabled=true;b.textContent='Analysing...'}};
</script></div></body></html>"""


def _badge(severity: str) -> str:
    if severity == "none":
        return '<span class="badge" style="background:#4ade80">NONE</span>'
    r, g, b = image_analysis.SEVERITY_COLORS[severity]
    return f'<span class="badge" style="background:rgb({r},{g},{b})">{severity.upper()}</span>'


def store_training_upload(filename: str, data: bytes, spacing: float, form: dict) -> str | None:
    """Save the upload with a consent record, only if the user explicitly opted in. Returns a reference id."""
    if form.get("training_consent") != "yes":
        return None
    ref = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    (TRAINING_DIR / f"{ref}_{filename}").write_bytes(data)
    record = {"ref": ref, "original_name": filename, "pixel_size_mm": spacing, "consent_version": CONSENT_VERSION,
              "consent_text": CONSENT_TEXT, "consented_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (TRAINING_DIR / f"{ref}.consent.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return ref


def render_result(filename: str, result: dict, retained_ref: str | None = None) -> str:
    storage = (f"Retained for tool development with your consent (reference {html.escape(retained_ref)})."
               if retained_ref else "Not retained: this image was analysed in memory and discarded.")
    imgs = "".join(
        f'<img class="result" alt="Annotated CT" src="data:image/png;base64,{base64.b64encode(p).decode("ascii")}">'
        for p in result["images"]
    )
    rows = "".join(
        "<tr><td>#{id}</td><td>{badge}</td><td>{kind}</td><td>{d:.1f} mm</td><td>{hu:.0f}</td><td>({x}, {y}){sl}</td></tr>".format(
            id=f["id"], badge=_badge(f["severity"]), kind=html.escape(f["kind"]), d=f["diameter_mm"],
            hu=f["mean_hu"], x=f["x"], y=f["y"], sl=f" slice {f['slice_index']}" if f["slice_index"] is not None else "",
        )
        for f in result["findings"]
    ) or '<tr><td colspan="6">No suspicious regions detected.</td></tr>'
    notes = "".join(f"<li>{html.escape(n)}</li>" for n in result["notes"])
    dominant = html.escape(result["dominant_finding"] or "-")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Lung CT Result</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>Analysis result</h1><div class="sub">{html.escape(filename)}</div>
<div class="card"><b>Overall:</b> {html.escape(result['label'])} &nbsp; {_badge(result['severity'])}
&nbsp; <b>Main finding:</b> {dominant}</div>
<div class="card">{imgs}</div>
<div class="card"><b>Marked regions</b><table><tr><th>ID</th><th>Severity</th><th>Type</th><th>Size</th><th>Mean HU</th><th>Position (x, y)</th></tr>{rows}</table>
<ul>{notes}</ul></div>
<div class="warn">Suspected regions are candidates only. Colour shows size-based severity, not a confirmed diagnosis.
Bright normal structures (vessels, bone, calcification) can be mis-marked. Consult a radiologist.</div>
<div class="card"><b>Data use:</b> {storage}</div>
<p><a href="/">Analyse another image</a></p></div></body></html>"""


def _error_page(message: str) -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="wrap">'
            f'<div class="warn">{html.escape(message)}</div><p><a href="/">Back</a></p></div></body></html>')


class LungGUIHandler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if urlparse(self.path).path in ("/", "/upload"):
            self._send(200, PAGE)
        else:
            self._send(404, _error_page("Not found"))

    def do_POST(self):
        if urlparse(self.path).path != "/analyse":
            self._send(404, _error_page("Not found"))
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > image_analysis.MAX_UPLOAD_BYTES:
            self._send(413, _error_page("Upload is empty or too large."))
            return
        form = _parse_multipart_form(self.rfile.read(length), self.headers.get("Content-Type", ""))
        upload = form.get("image")
        if not isinstance(upload, tuple) or not upload[1]:
            self._send(400, _error_page("No image uploaded."))
            return
        filename, payload = upload
        try:
            spacing = float(str(form.get("spacing") or 0.7).replace(",", "."))
            result = image_analysis.analyse_upload(_safe_name(filename), payload, spacing)
        except (ValueError, OSError) as exc:
            self._send(400, _error_page(str(exc)))
            return
        retained = store_training_upload(_safe_name(filename), payload, spacing, form)
        self._send(200, render_result(_safe_name(filename), result, retained))

    def log_message(self, *args, **kwargs):
        return


def run_server(host: str = HOST, port: int = PORT) -> None:
    server = HTTPServer((host, port), LungGUIHandler)
    print(f"Lung CT analysis GUI running at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping GUI...")
    finally:
        server.server_close()


def main() -> None:
    run_server()


if __name__ == "__main__":
    main()
