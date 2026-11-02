"""General, educational guidance shown with a result. Not a diagnosis or prescription."""
from __future__ import annotations

LEVELS = ["low", "moderate", "high", "critical"]

POSSIBLE_CAUSES = {
    "ground-glass nodule": [
        ("Infection or inflammation", "Viral or atypical pneumonia and organising pneumonia often look like this and may clear on their own."),
        ("Early lung adenocarcinoma spectrum", "If the area persists for weeks to months, specialists consider slow-growing early cancers."),
        ("Other causes", "Small bleeds, fluid, or reaction to medicines or irritants."),
    ],
    "part-solid nodule": [
        ("Adenocarcinoma spectrum", "A part-solid area that persists is more likely to need specialist assessment for early lung cancer."),
        ("Infection or inflammation", "A resolving pneumonia can look part-solid for a time."),
    ],
    "solid nodule": [
        ("Benign scar or granuloma", "Old, healed infection (for example tuberculosis or a fungal infection) is a common cause."),
        ("Intrapulmonary lymph node or hamartoma", "Harmless growths that are frequently found by chance."),
        ("Lung cancer or a spread from another cancer", "Less common for small nodules, more likely as size increases."),
    ],
    "spiculated solid nodule": [
        ("Primary lung cancer", "An irregular, spiky outline is a feature doctors take seriously."),
        ("Scar tissue or infection", "Some scars and infections also have irregular edges."),
        ("Metastasis", "A spread from a cancer elsewhere in the body."),
    ],
    "mass": [
        ("Lung cancer", "A mass (30 mm or larger) needs prompt assessment to exclude cancer."),
        ("Infection or abscess", "Tuberculosis, fungal infection, or a lung abscess can form masses."),
        ("Lymphoma or other tumours", "Less common causes your doctors will consider."),
    ],
}
POSSIBLE_CAUSES["mass (spiculated/irregular)"] = POSSIBLE_CAUSES["mass"]

NEXT_STEPS = {
    "none": [
        "No areas were marked, but this tool can miss small or subtle changes. If you have symptoms or risk factors, discuss them with your doctor regardless of this result.",
        "Keep this image and any report so they can be compared with future scans.",
    ],
    "low": [
        "Share this result with your doctor. Small areas are often followed with a repeat CT after an interval chosen by the clinician (guidelines such as Fleischner or Lung-RADS are commonly used).",
        "Compare with any earlier scans: an area that is unchanged for a long time is reassuring.",
    ],
    "moderate": [
        "Arrange a review with your doctor or a chest specialist (pulmonologist) in the coming weeks.",
        "A follow-up CT after a few months is a common approach; the doctor may recommend sooner depending on your history.",
    ],
    "high": [
        "Arrange a prompt review with a pulmonologist or radiologist. Ask for the scan to be assessed on a full diagnostic CT rather than a single image.",
        "Further tests your doctor may consider: contrast-enhanced CT, PET-CT, bronchoscopy or needle biopsy, and discussion by a multidisciplinary team.",
    ],
    "critical": [
        "Seek an urgent specialist appointment (pulmonology or oncology), ideally within days rather than weeks.",
        "Expected work-up: diagnostic chest CT with contrast, PET-CT, tissue sampling (biopsy), staging scans, and a multidisciplinary team review.",
    ],
}

MEDICATION_NOTES = [
    "No medicine treats an area seen on a scan until the cause is known. Treatment depends on the diagnosis made by your clinicians.",
    "If an infection is confirmed, a doctor may prescribe antibiotics, antivirals, antifungals or anti-tuberculosis treatment matched to test results.",
    "For inflammatory conditions such as organising pneumonia, specialists sometimes use corticosteroids.",
    "If lung cancer is confirmed, the oncology team chooses among surgery, radiotherapy, chemotherapy, targeted therapy and immunotherapy after biopsy, genetic testing and staging.",
    "Medicines for symptoms such as cough or pain should be chosen with your doctor or pharmacist, especially if you take other medicines or have allergies.",
    "Do not start, stop or change any medicine because of this report, and do not take leftover antibiotics or steroids. Bring a list of your current medicines and allergies to your appointment.",
]

PERSONAL_CARE = [
    "Do not smoke, and avoid second-hand smoke. Ask your doctor about stop-smoking support, which greatly improves lung health.",
    "Stay gently active, such as daily walking, as long as you feel well and your doctor has not advised otherwise. Rest when you are short of breath.",
    "Practise slow, deep breathing exercises a few times a day; a physiotherapist can teach techniques suited to you.",
    "Eat a balanced diet with plenty of fruit, vegetables and protein, drink enough fluids, and aim for regular, sufficient sleep.",
    "Ask your doctor about vaccinations that protect the lungs (influenza, pneumococcal, COVID-19).",
    "Avoid dust, chemical fumes and other lung irritants; check your home for radon if you live in an area where it occurs.",
    "Keep a short diary of symptoms (cough, breathlessness, weight change, fever) and attend every follow-up appointment.",
    "Looking after your mood matters too. Talk to someone you trust or ask your doctor about counselling or support groups if you feel anxious.",
]

URGENT_SIGNS = [
    "Coughing up blood",
    "Severe or worsening shortness of breath",
    "Chest pain, especially sudden or severe",
    "Fever with chills or confusion that does not settle",
    "Unexplained weight loss, or a cough lasting more than three weeks",
]


def guidance_for(result: dict) -> dict:
    """Build educational guidance from the analysis result."""
    findings = result.get("findings", [])
    severity = result.get("severity", "none")
    causes: list[tuple[str, str]] = []
    seen = set()
    for kind in sorted({f["kind"] for f in findings}, key=lambda k: -len(POSSIBLE_CAUSES.get(k, []))):
        for name, note in POSSIBLE_CAUSES.get(kind, []):
            if name not in seen:
                seen.add(name)
                causes.append((name, note))
    if not findings:
        causes = [("No suspicious area marked", "The tool found nothing to mark. Normal lung tissue, thin blood vessels and airways are expected on a healthy scan.")]
    return {
        "causes": causes,
        "next_steps": NEXT_STEPS.get(severity, NEXT_STEPS["none"]),
        "medications": MEDICATION_NOTES,
        "personal_care": PERSONAL_CARE,
        "urgent": URGENT_SIGNS,
    }
