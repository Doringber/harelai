"""Tests run without Ollama: they feed made-up model answers into the real checking and decision code."""
import copy
from pathlib import Path

from approval.__main__ import run_case
from approval.check import check
from approval.decide import build_result

ROOT = Path(__file__).resolve().parents[1]


def fact(value, quote=None):
    return {"value": value, "quote": quote or str(value)}


PATIENT = {"patient_name": fact("JOHNSON, MARGARET A."), "date_of_birth": fact("1952-03-15"), "mrn": fact("847291")}
GOOD = {
    "request": {
        "patient_name": fact("JOHNSON, MARGARET A."), "date_of_birth": fact("1952-03-15"),
        "case_id": fact("PA-2025-847291"), "procedure": fact("Robotic-Assisted Transbronchial Lung Biopsy"),
        "cpt_codes": fact(["31629", "31632", "77012"], "31629 31632 77012"),
        "diagnoses": fact(["J44.9 - Chronic obstructive pulmonary disease"], "J44.9 - Chronic obstructive pulmonary disease"),
        "requested_date": fact("2025-12-10"),
        "procedure_supported": fact(True, "optimal approach for this peripheral lesion"),
    },
    "clinical": {**PATIENT, "patient_name": fact("Margaret A Johnson"),
                 "suspicious_nodule": fact(True, "suspicious for malignancy"),
                 "tissue_sampling": fact(True, "tissue diagnosis is warranted")},
    "ct": {**PATIENT, "location": fact("right upper lobe, posterior segment"), "nodule_size": fact("18 x 15 mm"),
           "lung_rads": fact("4B", "Lung-RADS Category: 4B"),
           "suspicious_nodule": fact(True, "highly suspicious for primary lung malignancy"),
           "tissue_sampling": fact(True, "tissue sampling recommended")},
    "labs": {**PATIENT, "coagulation_status": fact("Normal", "No evidence of coagulopathy."),
             "labs_acceptable": fact(True, "suitable for invasive procedures")},
    "pft": {**PATIENT, "fev1_percent": fact(62.0, "FEV1 62% predicted"), "dlco_percent": fact(58.0, "DLCO 58% predicted"),
            "pulmonary_acceptable": fact(True, "would tolerate bronchoscopic procedures")},
}


def texts_for(answers):
    """Fake documents that contain exactly the good quotes."""
    return {role: " ".join(f["quote"] for f in GOOD[role].values()) for role in answers}


def review(answers):
    facts, issues = check(texts_for(answers), answers)
    return build_result(facts, issues, "test")


def test_complete_case_is_approved():
    result = review(copy.deepcopy(GOOD))
    assert result["recommendation"]["status"] == "APPROVE"
    assert result["patient"]["name"] == "Margaret A. Johnson"
    assert result["clinical_summary"]["fev1_percent"] == 62
    assert result["clinical_summary"]["finding"] == "Suspicious right upper lobe pulmonary nodule"
    assert "right upper lobe" in result["recommendation"]["reason"] and "COPD" in result["recommendation"]["reason"]


def test_missing_rule_needs_manual_review():
    answers = copy.deepcopy(GOOD)
    del answers["ct"]["tissue_sampling"], answers["clinical"]["tissue_sampling"]
    result = review(answers)
    assert result["recommendation"]["status"] == "MANUAL_REVIEW"
    assert "Tissue sampling recommended" in result["recommendation"]["reason"]


def test_contraindication_needs_manual_review():
    answers = copy.deepcopy(GOOD)
    answers["labs"]["contraindication"] = fact(True, "suitable for invasive procedures")
    assert review(answers)["recommendation"]["status"] == "MANUAL_REVIEW"


def test_invented_quote_is_dropped():
    answers = copy.deepcopy(GOOD)
    answers["ct"]["nodule_size"] = fact("30 x 30 mm", "a 30 x 30 mm mass")  # not in the document
    result = review(answers)
    assert result["clinical_summary"]["nodule_size"] is None
    assert any("ct.nodule_size" in i["detail"] for i in result["issues"])


def test_dropped_no_answer_blocks_approval():
    answers = copy.deepcopy(GOOD)
    answers["labs"]["labs_acceptable"] = fact(False, "this sentence is not in the report")
    assert review(answers)["recommendation"]["status"] == "MANUAL_REVIEW"


def test_dropped_no_contraindication_does_not_block():
    answers = copy.deepcopy(GOOD)
    answers["clinical"]["contraindication"] = fact(False, "null")  # bad quote, but it argued for approval
    assert review(answers)["recommendation"]["status"] == "APPROVE"


def test_number_must_appear_in_its_quote():
    answers = copy.deepcopy(GOOD)
    answers["pft"]["fev1_percent"] = fact(99.0, "FEV1 62% predicted")
    assert review(answers)["clinical_summary"]["fev1_percent"] is None


def test_date_formats_are_unified():
    answers = copy.deepcopy(GOOD)
    answers["pft"]["date_of_birth"] = fact("03/15/1952")
    texts = texts_for(answers)
    texts["pft"] += " 03/15/1952"
    facts, issues = check(texts, answers)
    assert facts["pft"]["date_of_birth"]["value"] == "1952-03-15"
    assert build_result(facts, issues, "test")["recommendation"]["status"] == "APPROVE"


def test_different_patient_blocks_approval():
    answers = copy.deepcopy(GOOD)
    answers["labs"]["date_of_birth"] = fact("1960-01-01")
    texts = texts_for(answers)
    texts["labs"] += " 1960-01-01"
    facts, issues = check(texts, answers)
    result = build_result(facts, issues, "test")
    assert result["recommendation"]["status"] == "MANUAL_REVIEW"
    assert "date_of_birth" in result["recommendation"]["reason"]


def test_missing_document_blocks_approval():
    answers = copy.deepcopy(GOOD)
    del answers["labs"]
    result = review(answers)
    assert result["recommendation"]["status"] == "MANUAL_REVIEW"
    assert "missing document: labs" in result["recommendation"]["reason"]


def test_real_pdfs_are_read_and_one_failure_does_not_stop_the_rest():
    seen = []

    def fake_model(role, text, model):
        seen.append(role)
        if role == "labs":
            raise RuntimeError("model crashed")
        assert "JOHNSON" in text  # the PDF text really reached the model
        return {}

    result = run_case(ROOT / "case.json", "fake", fake_model)
    assert seen == ["request", "clinical", "ct", "labs", "pft"]
    assert result["recommendation"]["status"] == "MANUAL_REVIEW"
    assert any("labs: could not process" in i["detail"] for i in result["issues"])
