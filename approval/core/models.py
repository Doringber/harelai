from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Role = Literal["request", "clinical", "ct", "labs", "pft"]
FieldName = Literal[
    "case_id", "name", "date_of_birth", "mrn", "provider", "procedure", "cpt_codes",
    "diagnoses", "requested_date", "facility", "finding", "nodule_size", "location",
    "characteristics", "lung_rads", "suv_max", "risk_brock_percent", "risk_mayo_percent",
    "fev1_percent", "dlco_percent", "coagulation_status", "laboratory_status", "rationale",
    "reported_age", "suspicious_nodule", "tissue_sampling", "procedure_supported",
    "labs_acceptable", "pulmonary_acceptable", "contraindication"]
BOOLEAN_FIELDS = {"suspicious_nodule", "tissue_sampling", "procedure_supported",
                  "labs_acceptable", "pulmonary_acceptable", "contraindication"}
NUMBER_FIELDS = {"suv_max", "risk_brock_percent", "risk_mayo_percent", "fev1_percent",
                 "dlco_percent", "reported_age"}
LIST_FIELDS = {"cpt_codes", "diagnoses"}

class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

class Page(Model):
    number: int = Field(ge=1)
    text: str
    method: Literal["native", "ocr", "docx", "text"]
    usable: bool = True
    warnings: list[str] = Field(default_factory=list)

class Document(Model):
    id: str
    filename: str
    role: Role
    sha256: str
    pages: list[Page]

class Evidence(Model):
    document_id: str
    page: int = Field(ge=1)
    quote: str = Field(min_length=3, max_length=2500)

class Observation(Model):
    field: FieldName
    value: str | float | bool | list[str]
    evidence: Evidence

    @model_validator(mode="after")
    def typed_value(self):
        v = self.value
        if self.field in BOOLEAN_FIELDS:
            if type(v) is not bool: raise ValueError("Boolean field requires true/false")
        elif self.field in NUMBER_FIELDS:
            if isinstance(v, bool) or not isinstance(v, (float, int)):
                raise ValueError("Numeric field requires number")
            if v < 0 or (self.field != "suv_max" and v > 120):
                raise ValueError("Number outside extraction plausibility range")
        elif self.field in LIST_FIELDS:
            if not isinstance(v, list) or not v: raise ValueError("Nonempty list required")
        elif not isinstance(v, str) or not v.strip():
            raise ValueError("Nonempty string required")
        return self

class Extraction(Model):
    observations: list[Observation]

class Issue(Model):
    code: str
    severity: Literal["warning", "blocking"]
    detail: str

class Criterion(Model):
    name: str
    met: bool
    evidence: list[Evidence]

class Recommendation(Model):
    status: Literal["APPROVE", "MANUAL_REVIEW"]
    reason: str
    criteria: list[Criterion]

class Result(Model):
    schema_version: str = "1"
    policy_version: str = "assignment-v1"
    run_id: str
    run_status: Literal["completed", "partial", "failed"]
    extraction_mode: str
    case_id: str | None
    patient: dict
    request: dict
    clinical_summary: dict
    recommendation: Recommendation
    issues: list[Issue]
    observations: list[Observation]
    documents: list[Document]
    trace: list[dict]
