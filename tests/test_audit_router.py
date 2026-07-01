"""Tests for the type-routed per-paper validity audit router."""
from paperscope.analysis.audit_router import (
    classify_study_type, ml_validity, audit_paper, PROFILES,
)


def test_classify_diagnostic_ml():
    t = "We propose a deep learning model for the diagnosis of disease X from CT images."
    assert classify_study_type(t) == "diagnostic_ml"


def test_classify_rct():
    t = ("This randomized controlled trial used a placebo-controlled, double-blind "
         "design with intention-to-treat analysis.")
    assert classify_study_type(t) == "rct"


def test_classify_prognostic():
    t = ("We build a survival analysis model and report the hazard ratio for "
         "mortality; this is a risk prediction study.")
    assert classify_study_type(t) == "prognostic"


def test_classify_other():
    assert classify_study_type("A short note about clinical workflows.") == "other"


def test_classify_review():
    t = "This systematic review of AI in prostate cancer imaging summarises recent work."
    assert classify_study_type(t) == "review"


def test_classify_discovery():
    t = "Using single-cell transcriptomes we built an atlas of immune cells in lung cancer."
    assert classify_study_type(t) == "discovery"


def test_classify_segmentation_is_method():
    t = "We propose a segmentation framework for vertebrae in spinal CT scans."
    assert classify_study_type(t) == "method"


def test_diagnostic_not_overcalled_by_background_diagnosis_mention():
    # exclusion-first: a segmentation paper mentioning 'diagnosis' in background must NOT
    # be labelled diagnostic_ml (the ~40%->~89% precision fix).
    t = ("Vertebrae segmentation plays a critical role in the diagnosis and treatment of "
         "spinal disorders; we present a new segmentation network.")
    assert classify_study_type(t) == "method"


def test_ml_validity_flags():
    t = ("We performed external validation in an independent cohort, reported 95% CI, "
         "used SMOTE for class imbalance, and a patient-level split to prevent leakage; "
         "we distinguish disease from its differential diagnosis.")
    v = ml_validity(t)
    assert v["external_validation"]
    assert v["reports_ci"]
    assert v["imbalance_addressed"]
    assert v["leakage_addressed"]
    assert v["comparator"] == "mimic_differential"


def test_ml_validity_unclear_comparator():
    assert ml_validity("a model with no comparison stated")["comparator"] == "unclear"


def test_audit_paper_routes_diagnostic_battery_without_embeddings():
    t = ("A convolutional neural network for diagnosis of cancer from histopathology "
         "slides, with external validation in an independent cohort.")
    rec = audit_paper(t, run_overclaiming=False)
    assert rec["study_type"] == "diagnostic_ml"
    assert rec["battery"] == PROFILES["diagnostic_ml"]
    assert "ml_validity" in rec
    assert rec["ml_validity"]["external_validation"] is True
    # overclaiming skipped -> no score key
    assert "overclaiming_score" not in rec


def test_audit_paper_rct_forensic_stats_skipped_without_tables():
    t = ("A randomized controlled trial, placebo-controlled and double-blind, "
         "evaluating drug Y.")
    rec = audit_paper(t, run_overclaiming=False)
    assert rec["study_type"] == "rct"
    assert "forensic_stats" in rec  # skipped note, since no table_data supplied
