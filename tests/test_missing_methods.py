"""Regression tests for method-name auto-detection."""

from paperscope.analysis.missing_methods import (
    detect_method_candidates,
    detect_methods,
)
from paperscope.analysis.critical_read import (
    _accepted_method_names,
    _method_detection_text,
)


def test_detect_methods_ignores_theory_prose_false_positives():
    text = (
        "The coherent order can relax when local processing is needed. "
        "Experience may fade toward a ground regime. "
        "The paper studies SU(3) Cartan-root structure and MR thermography. "
        "Indices fabc and fbabc encode algebraic structure constants."
    )

    assert detect_methods(text) == []
    candidates = detect_method_candidates(text)
    weak = {c["matched_from"]: c for c in candidates if not c["accepted"]}
    assert weak["relax"]["reason"] == "requires_uppercase_tool_name"
    assert weak["fade"]["reason"] == "requires_uppercase_tool_name"
    assert weak["structure"]["reason"] == "requires_uppercase_tool_name"
    assert weak["mr"]["reason"] == "bare_alias_disabled"


def test_detect_methods_requires_context_for_structure_tool():
    plain = "Population STRUCTURE is a recurring biological concept."
    methods = "We estimated population clusters using STRUCTURE software."

    assert "ADMIXTURE / STRUCTURE" not in detect_methods(plain)
    assert "ADMIXTURE / STRUCTURE" in detect_methods(methods)


def test_detect_methods_accepts_explicit_uppercase_tools():
    text = (
        "We ran RELAX and MEME using HyPhy. "
        "We also performed PCA analysis and used ADMIXTURE software."
    )

    methods = detect_methods(text)
    assert "RELAX" in methods
    assert "MEME" in methods
    assert "PCA" in methods
    assert "ADMIXTURE / STRUCTURE" in methods


def test_detect_methods_does_not_treat_mr_as_mendelian_randomization():
    assert detect_methods("MR thermography was used for thermal monitoring.") == []
    assert "Mendelian Randomization" in detect_methods(
        "We used Mendelian Randomization with genetic instruments."
    )


def test_detect_methods_requires_context_for_short_acronyms():
    assert "Approximate Bayesian Computation" not in detect_methods(
        "The equation uses indices a, b, c and sometimes ABC-like notation."
    )
    assert "Approximate Bayesian Computation" in detect_methods(
        "We used ABC analysis for simulator-based inference."
    )


def test_method_detection_text_prefers_method_sections():
    sections = {
        "abstract": "The abstract mentions STRUCTURE in ordinary prose.",
        "methods": "We ran RELAX using HyPhy.",
        "references": "A cited paper used PCA.",
    }

    text, scope = _method_detection_text(sections, "full paper")
    assert scope == "method_sections"
    assert "RELAX" in text
    assert "PCA" not in text


def test_method_detection_text_front_matter_fallback_is_bounded():
    sections = {"abstract": "no method section"}
    paper = "front " + ("x" * 13000) + " We ran RELAX using HyPhy."

    text, scope = _method_detection_text(sections, paper)
    assert scope == "front_matter_fallback"
    assert len(text) == 12000
    assert "RELAX" not in text


def test_accepted_method_names_deduplicates_candidate_scaffold():
    candidates = detect_method_candidates("We ran RELAX and used HyPhy RELAX.")

    assert _accepted_method_names(candidates) == ["RELAX"]
    assert any(c["accepted"] for c in candidates)
