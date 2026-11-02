"""Browser GUI: upload a lung CT image, mark suspected lesions with severity colours."""
from __future__ import annotations

import base64
import html
import json
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import clinical_info, image_analysis, security
from .ct_upload_demo import _parse_multipart_form, _safe_name

HOST = os.environ.get("LUNG_GUI_HOST", "127.0.0.1")
PORT = int(os.environ.get("GUI_PORT") or os.environ.get("PORT") or 8005)
TRAINING_DIR = Path(__file__).resolve().parents[2] / "data" / "training_uploads"
CONSENT_VERSION = "2026-11-v1"
CONSENT_TEXT = (
    "I consent to my uploaded CT image being retained and used to develop, test and improve the analysis "
    "module of this tool (for example evaluating or training lesion-detection models). I confirm I am "
    "authorised to share this image and have removed patient-identifying information (name, ID, dates, DICOM metadata)."
)

CSS = """
:root{--navy:#000;--blue:#0b6f8a;--ink:#000;--muted:#333;--line:#cfd8dc;--bg:#fff;--card:#fff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI",system-ui,-apple-system,Arial,sans-serif;line-height:1.55}
header{background:#fff;border-top:6px solid var(--blue);border-bottom:1px solid var(--line);color:#000;padding:18px 0}
.wrap{max-width:980px;margin:0 auto;padding:0 24px}
header h1{margin:0;font-size:26px;font-weight:600;color:#000;display:flex;align-items:center;gap:14px}
header h1::before{content:"";flex:none;width:38px;height:38px;border-radius:8px;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 38 38'%3E%3Crect width='38' height='38' rx='8' fill='%230b6f8a'/%3E%3Crect x='16' y='8' width='6' height='22' fill='white'/%3E%3Crect x='8' y='16' width='22' height='6' fill='white'/%3E%3C/svg%3E") no-repeat center/contain}
header p{margin:4px 0 0 52px;color:#333;font-size:15px}
main{padding:28px 0 48px}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:24px;margin-bottom:20px}
h2{margin:0 0 6px;font-size:18px;color:var(--navy)}
.lead{color:var(--muted);margin:0 0 16px}
.step{display:flex;gap:16px;align-items:flex-start;margin-top:22px}
.step .n{flex:none;width:30px;height:30px;border-radius:50%;background:var(--blue);color:#fff;text-align:center;line-height:30px;font-weight:600;font-size:14px}
.step .body{flex:1}
.drop{border:2px dashed #90a4ae;border-radius:6px;padding:30px;text-align:center;cursor:pointer;background:#fafafa;color:#333}
.drop:hover,.drop.over{background:#e8f4f8;border-color:var(--blue)}
.drop strong{color:var(--navy)}
.drop small{display:block;margin-top:6px}
input[type=number]{border:1px solid #b8c6d4;border-radius:6px;padding:9px 10px;width:130px;font-size:15px}
.hint{color:var(--muted);font-size:13px;margin-top:6px}
.consent{background:#fafafa;border:1px solid var(--line);border-radius:6px;padding:16px;font-size:14px}
label.chk{display:flex;gap:12px;align-items:flex-start;cursor:pointer}
label.chk input{margin-top:5px;width:17px;height:17px;flex:none}
.consent p{color:var(--muted);margin:12px 0 0;font-size:13px}
button,.btn{display:inline-block;background:var(--blue);color:#fff;border:0;border-radius:6px;padding:12px 26px;font-size:16px;font-weight:600;cursor:pointer;text-decoration:none}
button:hover,.btn:hover{background:#095a70}
button:disabled{background:#8a99a8;cursor:wait}
.notice{background:#fff8e6;border:1px solid #ecd48a;color:#5c4a12;border-radius:8px;padding:14px 16px;font-size:14px}
.summary{display:flex;gap:18px;align-items:center}
.summary .big{flex:none}
.summary p{margin:0}
.summary .headline{font-size:19px;color:var(--navy);font-weight:600;margin-bottom:4px}
img.result{max-width:100%;border:1px solid var(--line);border-radius:8px;display:block;margin-top:12px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.badge{display:inline-block;padding:3px 12px;border-radius:999px;color:#1a1a1a;font-weight:700;font-size:12px;letter-spacing:.03em}
.badge.lg{font-size:14px;padding:7px 18px}
.guide{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:12px}
.guide div{border:1px solid var(--line);border-radius:8px;padding:12px;font-size:14px}
.dot{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:8px;vertical-align:-1px}
.muted{color:var(--muted);font-size:14px}
footer{color:var(--muted);font-size:13px;text-align:center;padding:0 24px 32px}
a{color:var(--blue)}
ul{margin:8px 0 0;padding-left:22px}li{margin-bottom:6px}
.urgent{background:#fdecea;border:1px solid #e5a29b;border-radius:6px;padding:14px 18px;margin-bottom:20px;font-size:14px;color:#000}
.urgent ul{margin:6px 0 0}
@page{size:A4;margin:14mm}
.toolbar{display:flex;gap:12px;margin-bottom:18px}
.btn.secondary,button.secondary{background:#fff;color:var(--blue);border:1px solid var(--blue)}
.btn.secondary:hover,button.secondary:hover{background:#e8f4f8}
input[type=password]{border:1px solid #b8c6d4;border-radius:6px;padding:9px 10px;width:100%;max-width:360px;font-size:15px}
@media print{
*{-webkit-print-color-adjust:exact;print-color-adjust:exact}
.btn,.noprint{display:none!important}
body{font-size:12px}
main{padding:12px 0}
.card,.urgent,.notice{break-inside:avoid}
h2{break-after:avoid}
img.result{max-width:100%;break-inside:avoid}
footer{padding-bottom:0}
}
"""

PAGE = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Lung CT Lesion Analysis</title>
<style>{CSS}</style></head><body>
<header><div class="wrap"><h1>Lung CT Lesion Analysis</h1>
<p>Image-assisted review of suspected lung lesions</p></div></header>
<main><div class="wrap">
<form id="f" action="/analyse" method="post" enctype="multipart/form-data">
<div class="card">
<h2>Review a chest CT image</h2>
<p class="lead">Upload an image and the tool will mark any areas that may deserve a closer look, using colour to show
how significant each area appears based on its size. It takes a few seconds.</p>

<div class="step"><div class="n">1</div><div class="body"><b>Choose your image</b>
<div class="drop" id="drop" style="margin-top:10px"><span id="msg"><strong>Click to choose a file</strong> or drag it here
<small>PNG, JPG, TIFF or BMP (one axial slice), or a NIfTI volume (.nii, .nii.gz)</small></span></div>
<input id="file" name="image" type="file" accept=".png,.jpg,.jpeg,.tif,.tiff,.bmp,.nii,.nii.gz" hidden required></div></div>

<div class="step"><div class="n">2</div><div class="body"><b>Confirm the pixel size</b>
<div style="margin-top:10px"><input id="spacing" name="spacing" type="number" step="0.01" min="0.05" max="5" value="0.7"> mm per pixel</div>
<div class="hint">Used to convert measurements to millimetres for ordinary images. A typical chest CT is between 0.6 and 0.9.
Not needed for NIfTI volumes, which carry their own scale.</div></div></div>

<div class="step"><div class="n">3</div><div class="body"><b>Data use (optional)</b>
<div class="consent" style="margin-top:10px">
<label class="chk"><input name="training_consent" type="checkbox" value="yes"> <span>{html.escape(CONSENT_TEXT)}</span></label>
<p>This is entirely optional. If you leave it unticked, your image is analysed in memory and discarded as soon as the result is shown.
If you tick it, the image is saved on the computer running this tool, together with a record of your consent, and is used only to develop this tool.
You can ask the operator to delete it at any time. Please do not tick this box for images that still contain identifying information.</p></div></div></div>

<div style="margin-top:26px"><button id="go" type="submit">Analyse image</button></div>
</div></form>
<div class="notice"><b>Please note.</b> This is a research tool built on simple image-processing rules. It has not been clinically validated,
may miss real lesions, and may mark normal structures such as blood vessels. It cannot diagnose disease and does not replace the opinion of a radiologist or physician.</div>
</div></main>
<footer>For research and education only.</footer>
<script>
const drop=document.getElementById('drop'),file=document.getElementById('file'),msg=document.getElementById('msg');
drop.onclick=()=>file.click();
file.onchange=()=>{{if(file.files[0])msg.innerHTML='<strong>'+file.files[0].name.replace(/[<>&]/g,'')+'</strong><small>Ready to analyse</small>'}};
drop.ondragover=e=>{{e.preventDefault();drop.classList.add('over')}};
drop.ondragleave=()=>drop.classList.remove('over');
drop.ondrop=e=>{{e.preventDefault();drop.classList.remove('over');file.files=e.dataTransfer.files;file.onchange()}};
document.getElementById('f').onsubmit=()=>{{const b=document.getElementById('go');b.disabled=true;b.textContent='Analysing, please wait...'}};
</script></body></html>"""

PLAIN_SEVERITY = {
    "none": "No areas were marked",
    "low": "Small area",
    "moderate": "Moderate-sized area",
    "high": "Larger area",
    "critical": "Large area or mass",
}


def _badge(severity: str, large: bool = False) -> str:
    cls = "badge lg" if large else "badge"
    if severity == "none":
        return f'<span class="{cls}" style="background:#b7e4c7">NONE</span>'
    r, g, b = image_analysis.SEVERITY_COLORS[severity]
    text = "#fff" if severity in ("high", "critical") else "#1a1a1a"
    return f'<span class="{cls}" style="background:rgb({r},{g},{b});color:{text}">{severity.upper()}</span>'


def _normal_reference() -> bytes:
    global _NORMAL_PNG
    if _NORMAL_PNG is None:
        _NORMAL_PNG = image_analysis.normal_reference_png()
    return _NORMAL_PNG


_NORMAL_PNG: bytes | None = None


def _headline(result: dict) -> tuple[str, str]:
    findings = result["findings"]
    if not findings:
        return ("No suspicious areas were marked on this image.",
                "That is not a guarantee that the image is normal. Small or subtle lesions may not be detected by this tool.")
    n = len(findings)
    worst = [f for f in findings if f["severity"] == result["severity"]]
    top = max(worst or findings, key=lambda f: f["diameter_mm"])
    count = "1 area was" if n == 1 else f"{n} areas were"
    return (f"{count} marked for closer review.",
            f"The most significant is a {html.escape(top['kind'])} of about {top['diameter_mm']:.0f} mm, "
            f"rated {result['severity']}. Please have these areas reviewed by a qualified clinician.")


def store_training_upload(filename: str, data: bytes, spacing: float, form: dict) -> str | None:
    """Save the upload with a consent record, only if the user explicitly opted in. Returns a reference id."""
    if form.get("training_consent") != "yes" or security.demo_mode():
        return None
    if security.dir_size(TRAINING_DIR) + len(data) > security.max_store_bytes():
        return None
    ref = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    (TRAINING_DIR / f"{ref}_{filename}").write_bytes(data)
    record = {"ref": ref, "original_name": filename, "pixel_size_mm": spacing, "consent_version": CONSENT_VERSION,
              "consent_text": CONSENT_TEXT, "consented_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (TRAINING_DIR / f"{ref}.consent.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return ref


def render_result(filename: str, result: dict, retained_ref: str | None = None) -> str:
    storage = (f"Your image was kept for tool development with your consent (reference {html.escape(retained_ref)})."
               if retained_ref else "Your image was not kept. It was analysed in memory and discarded.")
    imgs = "".join(
        f'<img class="result" alt="CT image with suspected areas marked" src="data:image/png;base64,{base64.b64encode(p).decode("ascii")}">'
        for p in result["images"]
    )
    rows = "".join(
        "<tr><td>{id}</td><td>{badge}</td><td>{kind}</td><td>{d:.1f} mm</td><td>{hu:.0f}</td><td>{x}, {y}{sl}</td></tr>".format(
            id=f["id"], badge=_badge(f["severity"]), kind=html.escape(f["kind"]).capitalize(), d=f["diameter_mm"],
            hu=f["mean_hu"], x=f["x"], y=f["y"], sl=f" (slice {f['slice_index']})" if f["slice_index"] is not None else "",
        )
        for f in result["findings"]
    ) or '<tr><td colspan="6">No suspicious areas were detected.</td></tr>'
    notes = "".join(f"<li>{html.escape(n)}</li>" for n in result["notes"])
    guide = "".join(
        '<div><span class="dot" style="background:rgb{c}"></span><b>{n}</b><br><span class="muted">{r}</span></div>'.format(
            c=image_analysis.SEVERITY_COLORS[name], n=name.capitalize(), r=rule)
        for name, rule in image_analysis.LEGEND
    )
    headline, detail = _headline(result)
    info = clinical_info.guidance_for(result)
    causes = "".join(f"<li><b>{html.escape(n)}.</b> {html.escape(t)}</li>" for n, t in info["causes"])
    steps = "".join(f"<li>{html.escape(t)}</li>" for t in info["next_steps"])
    meds = "".join(f"<li>{html.escape(t)}</li>" for t in info["medications"])
    care = "".join(f"<li>{html.escape(t)}</li>" for t in info["personal_care"])
    urgent = "".join(f"<li>{html.escape(t)}</li>" for t in info["urgent"])
    normal_img = base64.b64encode(_normal_reference()).decode("ascii")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Analysis result</title>
<style>{CSS}</style></head><body>
<header><div class="wrap"><h1>Lung CT Lesion Analysis</h1><p>Result for {html.escape(filename)} &middot; Report generated {time.strftime('%d %b %Y %H:%M', time.gmtime())} UTC</p></div></header>
<main><div class="wrap">
<div class="toolbar noprint"><button type="button" onclick="window.print()">Save as PDF / Print</button>
<a class="btn secondary" href="/">Analyse another image</a></div>
<p class="muted noprint" style="margin-top:-6px">In the print window, choose &ldquo;Save as PDF&rdquo; as the destination.</p>
<div class="card summary"><div class="big">{_badge(result['severity'], True)}</div>
<div><p class="headline">{headline}</p><p class="muted">{detail}</p></div></div>

<div class="card"><h2>Marked image</h2>
<p class="lead">Coloured outlines show where the tool found areas that look different from surrounding lung tissue.
The label beside each outline gives its number, approximate size and rating.</p>{imgs}</div>

<div class="card"><h2>Details of each marked area</h2>
<table><tr><th>No.</th><th>Rating</th><th>Appearance</th><th>Approx. size</th><th>Density (HU)</th><th>Position (x, y)</th></tr>{rows}</table>
<ul class="muted">{notes}</ul></div>

<div class="card"><h2>Possible explanations</h2>
<p class="lead">General information about what areas like these can represent. Only a clinician, using your history, examination and further tests, can make a diagnosis.</p>
<ul>{causes}</ul></div>

<div class="card"><h2>Suggested next steps</h2><ul>{steps}</ul></div>

<div class="card"><h2>About medicines</h2>
<p class="lead">General education only. This is not a prescription and no doses are suggested.</p>
<ul>{meds}</ul></div>

<div class="card"><h2>Personal care and recommended activity</h2><ul>{care}</ul></div>

<div class="urgent"><b>Seek urgent medical care if you have:</b><ul>{urgent}</ul></div>

<div class="card"><h2>How to read these ratings</h2>
<p class="lead">Ratings reflect size and shape only. An irregular outline or a part-solid appearance raises the rating by one level.</p>
<div class="guide">{guide}</div></div>

<div class="card"><h2>For comparison: a typical normal chest CT</h2>
<p class="lead">In a healthy chest the lungs appear evenly dark, with thin branching blood vessels and no isolated bright round spots. This is a schematic illustration, not a patient scan. The tool looks for areas that stand out from this normal pattern.</p>
<img class="result" style="max-width:520px" alt="Schematic of a normal chest CT" src="data:image/png;base64,{normal_img}"></div>

<div class="card"><h2>Your data</h2><p class="muted" style="margin:0">{storage}</p></div>

<div class="notice"><b>Important.</b> These are candidate areas only, not a diagnosis. Normal structures such as blood vessels, bone or
calcification can be marked by mistake, and real lesions can be missed. Please discuss your scan with a radiologist or physician.</div>
<p style="margin-top:22px" class="noprint"><button type="button" onclick="window.print()">Save as PDF / Print</button>
<a class="btn secondary" href="/">Analyse another image</a></p>
</div></main><footer>For research and education only.</footer></body></html>"""


def _error_page(message: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Unable to analyse</title><style>{CSS}</style></head><body>'
            f'<header><div class="wrap"><h1>Lung CT Lesion Analysis</h1></div></header>'
            f'<main><div class="wrap"><div class="card"><h2>We could not analyse that file</h2>'
            f'<p class="muted">{html.escape(message)}</p><p><a class="btn" href="/">Try again</a></p></div></div></main></body></html>')


DEMO_STEP = ('<div class="step"><div class="n">3</div><div class="body"><b>Data use</b>'
             '<div class="consent" style="margin-top:10px"><p style="margin:0">This is a demonstration. Uploaded images are analysed in memory and are '
             'never saved, and no consent is requested. Please use only anonymised or sample images.</p></div></div></div>')


def render_upload_page() -> str:
    if not security.demo_mode():
        return PAGE
    return re.sub(r'<div class="step"><div class="n">3</div>.*?(?=<div style="margin-top:26px">)', DEMO_STEP + "\n\n", PAGE, flags=re.S)


def _login_page(error: str = "") -> str:
    msg = f'<p class="muted" style="color:#a40000">{html.escape(error)}</p>' if error else ""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Sign in</title><style>{CSS}</style></head><body>'
            f'<header><div class="wrap"><h1>Lung CT Lesion Analysis</h1><p>Access is restricted</p></div></header>'
            f'<main><div class="wrap"><div class="card"><h2>Enter the access code</h2>'
            f'<p class="lead">Ask the person who shared this link for the access code.</p>{msg}'
            f'<form action="/login" method="post"><input type="password" name="token" autocomplete="current-password" required autofocus>'
            f'<div style="margin-top:16px"><button type="submit">Continue</button></div></form></div></div></main></body></html>')


_LIMITER = security.RateLimiter()
_ANALYSIS_SLOTS = threading.BoundedSemaphore(2)


class LungGUIHandler(BaseHTTPRequestHandler):
    timeout = 60

    def _client_ip(self) -> str:
        if security.trust_proxy():
            forwarded = self.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return self.client_address[0]

    def _send(self, status: int, body: str, extra_headers: dict | None = None) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; form-action 'self'")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def _authed(self) -> bool:
        return security.cookie_is_valid(self.headers.get("Cookie"), security.access_token())

    def do_GET(self):
        if urlparse(self.path).path == "/healthz":
            self._send(200, "ok")
            return
        if urlparse(self.path).path not in ("/", "/upload"):
            self._send(404, _error_page("That page does not exist."))
        elif not self._authed():
            self._send(401, _login_page())
        else:
            self._send(200, render_upload_page())

    def _login(self) -> None:
        if not _LIMITER.allow("login:" + self._client_ip(), 5):
            self._send(429, _login_page("Too many attempts. Please wait a minute and try again."))
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        if not 0 < length <= 2048:
            self._send(400, _login_page("Invalid request."))
            return
        supplied = parse_qs(self.rfile.read(length).decode("utf-8", "replace")).get("token", [""])[0]
        token = security.access_token()
        if not security.token_matches(supplied, token):
            self._send(401, _login_page("That access code is not correct."))
            return
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        cookie = f"{security.COOKIE_NAME}={security.session_value(token)}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{secure}"
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/login" and security.access_token():
            self._login()
            return
        if path != "/analyse":
            self._send(404, _error_page("That page does not exist."))
            return
        if not self._authed():
            self._send(401, _login_page())
            return
        if not _LIMITER.allow("analyse:" + self._client_ip(), security.rate_limit_per_minute()):
            self._send(429, _error_page("Too many requests. Please wait a minute and try again."))
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > security.max_upload_bytes():
            limit_mb = security.max_upload_bytes() // security.MB
            self._send(413, _error_page(f"The upload is empty or larger than the {limit_mb} MB limit."))
            return
        form = _parse_multipart_form(self.rfile.read(length), self.headers.get("Content-Type", ""))
        upload = form.get("image")
        if not isinstance(upload, tuple) or not upload[1]:
            self._send(400, _error_page("No image was uploaded."))
            return
        filename, payload = upload
        if not _ANALYSIS_SLOTS.acquire(blocking=False):
            self._send(503, _error_page("The tool is busy with other analyses. Please try again shortly."))
            return
        try:
            spacing = float(str(form.get("spacing") or 0.7).replace(",", "."))
            result = image_analysis.analyse_upload(_safe_name(filename), payload, spacing)
        except (ValueError, OSError) as exc:
            self._send(400, _error_page(str(exc)))
            return
        finally:
            _ANALYSIS_SLOTS.release()
        retained = store_training_upload(_safe_name(filename), payload, spacing, form)
        self._send(200, render_result(_safe_name(filename), result, retained))

    def log_message(self, *args, **kwargs):
        return


def run_server(host: str = HOST, port: int = PORT) -> None:
    problem = security.refuse_open_exposure(host)
    if problem:
        raise SystemExit(problem)
    server = ThreadingHTTPServer((host, port), LungGUIHandler)
    server.daemon_threads = True
    mode = "demo mode (uploads never saved), " if security.demo_mode() else ""
    auth = "access code required" if security.access_token() else "no access code"
    print(f"Lung CT analysis GUI running at http://{host}:{port}/  [{mode}{auth}, upload limit {security.max_upload_bytes() // security.MB} MB]")
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
