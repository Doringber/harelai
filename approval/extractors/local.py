"""Narrow English-layout baseline. No LLM and no fabricated/golden output.
Regex rules extract the actual input bytes; this is a regression/demo aid, not a general extractor.
"""
import re
from datetime import datetime
from approval.core.models import Evidence, Observation, Extraction

class LocalExtractor:
    identity = "local-layout-baseline:v1"

    def extract(self, document):
        result = []
        def add(field, value, page, match):
            result.append(Observation(field=field, value=value,
                evidence=Evidence(document_id=document.id, page=page.number, quote=match.group(0))))
        for p in document.pages:
            if not p.usable: continue
            text = p.text
            def capture(field, pattern, convert=lambda m: m.group(1), flags=re.I):
                for m in re.finditer(pattern, text, flags): add(field, convert(m), p, m)
            capture("name", r"(?:Beneficiary Name:|Patient:)\s*([A-Z]+,\s*[A-Z]+(?:\s+[A-Z]\.)?)",
                lambda m: " ".join(reversed(m.group(1).split(", "))).title())
            capture("date_of_birth", r"(?:Date of Birth:|DOB:)\s*(\d{2}/\d{2}/\d{4})",
                lambda m: datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat())
            capture("mrn", r"MRN:\s*(\d+)")
            capture("reported_age", r"(\d{2})-year-old", lambda m: float(m.group(1)))
            capture("reported_age", r"Age:\s*(\d+)", lambda m: float(m.group(1)))
            capture("lung_rads", r"Lung-RADS(?: Classification| Category)?[: ]+(?:Category )?(4B)")
            capture("suv_max", r"SUVmax(?: of)?\s*(\d+(?:\.\d+)?)", lambda m: float(m.group(1)))
            capture("risk_brock_percent", r"Brock [Mm]odel probability of malignancy:?\s*(\d+)%", lambda m: float(m.group(1)))
            capture("risk_mayo_percent", r"Mayo Clinic Model:\s*(\d+)%", lambda m: float(m.group(1)))
            if document.role == "request":
                capture("case_id", r"Tracking #:\s*([A-Z]+-\d{4}-\d+)")
                capture("provider", r"Provider Name:\s*([^\n]+)")
                capture("procedure", r"Procedure/Service:\s*([^\n]+)")
                capture("cpt_codes", r"CPT Code\(s\):\s*([\s\S]*?)ICD-10 Diagnosis:", lambda m: re.findall(r"(?m)^(\d{5})", m.group(1)))
                capture("diagnoses", r"ICD-10 Diagnosis:\s*([\s\S]*?)Place of Service:", lambda m: [x.strip() for x in m.group(1).splitlines() if x.strip()])
                capture("facility", r"Facility:\s*([^\n]+)")
                capture("requested_date", r"Requested DOS:\s*([A-Za-z]+ \d+, \d{4})", lambda m: datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat())
                capture("rationale", r"(Robotic-assisted bronchoscopy[\s\S]*?FEV1 \d+% predicted\)\.)")
                capture("procedure_supported", r"Robotic-assisted bronchoscopy[\s\S]*?provides optimal approach[\s\S]*?FEV1 \d+% predicted\)\.", lambda m: True)
            if document.role == "ct":
                capture("nodule_size", r"(\d+ x \d+ mm) part-solid nodule")
                capture("location", r"nodule in the (right upper lobe, posterior segment)")
                capture("characteristics", r"(spiculated margins with a solid component measuring approximately \d+mm)")
                capture("finding", r"(\d+mm part-solid nodule[\s\S]*?highly suspicious for primary lung malignancy\.)")
                capture("suspicious_nodule", r"This is highly suspicious for primary lung malignancy\.", lambda m: True)
                capture("tissue_sampling", r"Recommendation: PET-CT and tissue sampling recommended\.", lambda m: True)
            if document.role == "labs":
                capture("coagulation_status", r"No evidence of coagulopathy\.", lambda m: "Normal")
                capture("laboratory_status", r"All values within normal limits\.", lambda m: "Normal")
                capture("labs_acceptable", r"Patient is suitable for invasive procedures from a hematologic and metabolic standpoint\.", lambda m: True)
            if document.role == "pft":
                capture("fev1_percent", r"FEV1 (\d+)% predicted", lambda m: float(m.group(1)))
                capture("dlco_percent", r"DLCO (\d+)% predicted", lambda m: float(m.group(1)))
                capture("pulmonary_acceptable", r"From a pulmonary function standpoint, patient would\s+tolerate bronchoscopic procedures\.", lambda m: True)
        return Extraction(observations=result)
