"""End-to-end tests for the forensic CLI (text mode, table mode, --annotate).

Generates the synthetic demo paper from examples/forensic/make_demo_paper.py
into tmp_path, drives `python3 -m paperscope forensic` via subprocess, and
checks the planted errors come back with the right verdicts, pages, and
anchors.  Self-contained -- no external corpus needed.

  python tests/test_forensic_cli_e2e.py   # standalone, prints PASS/FAIL
  pytest tests/test_forensic_cli_e2e.py   # under pytest
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

# examples/ is not a package: load the demo generator straight from its file
_GEN_PATH = ROOT / "examples" / "forensic" / "make_demo_paper.py"
_spec = importlib.util.spec_from_file_location("make_demo_paper", _GEN_PATH)
make_demo_paper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_demo_paper)

TABLE1 = ROOT / "examples" / "forensic" / "table1.json"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run `python3 -m paperscope forensic ...` from the repo root."""
    return subprocess.run(
        [sys.executable, "-m", "paperscope", "forensic", *map(str, args)],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )


def _demo_pdf(tmp: Path) -> Path:
    pdf = tmp / "demo-paper.pdf"
    make_demo_paper.build_demo_pdf(pdf)
    assert pdf.exists()
    return pdf


def test_text_mode_finds_planted_fails():
    tmp = Path(tempfile.mkdtemp())
    pdf = _demo_pdf(tmp)
    out = tmp / "report.json"

    proc = _run_cli(pdf, "-o", out)
    assert proc.returncode == 0, proc.stderr
    assert out.exists()
    report = json.loads(out.read_text(encoding="utf-8"))

    assert report["mode"] == "text"
    assert report["counts"]["FAIL"] >= 2, report["summary"]

    fails = [f for f in report["findings"] if f["verdict"] == "FAIL"]
    # Planted decision error: t(38) = 1.02 reported as p = .003
    decision = [f for f in fails if f["anchor"].startswith("t(38) = 1.02")]
    assert decision, [f["anchor"] for f in fails]
    # Planted impossible correlation: r(24) = 1.07
    impossible = [f for f in fails if f["anchor"].startswith("r(24) = 1.07")]
    assert impossible, [f["anchor"] for f in fails]

    # Both live in the Results section on page 2 (1-based), and each
    # anchor must be exact source text on its page
    doc = fitz.open(str(pdf))
    for f in decision + impossible:
        assert f["page"] == 2, f
        page_text = doc[f["page"] - 1].get_text()
        assert f["anchor"] in page_text, f["anchor"]
    doc.close()

    # The planted PASS and FLAG round out the counts; a parsing problem
    # must never have hardened anything
    assert report["counts"]["PASS"] >= 1
    assert report["counts"]["FLAG"] >= 1


def test_text_mode_annotate_produces_pdf():
    tmp = Path(tempfile.mkdtemp())
    pdf = _demo_pdf(tmp)
    out = tmp / "report.json"
    annotated = tmp / "annotated.pdf"

    proc = _run_cli(pdf, "-o", out, "--annotate", annotated)
    assert proc.returncode == 0, proc.stderr
    assert annotated.exists()

    src = fitz.open(str(pdf))
    ann = fitz.open(str(annotated))
    # front matter + interleaved commentary pages only ever add pages
    assert ann.page_count >= src.page_count
    src.close()
    ann.close()


def test_table_mode_finds_grim_fail():
    tmp = Path(tempfile.mkdtemp())
    out = tmp / "table-report.json"

    proc = _run_cli(TABLE1, "-o", out)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))

    assert report["mode"] == "table"
    # The classic GRIM failure: mean 18.72 is impossible for n = 22
    grim_fails = [f for f in report["findings"]
                  if f["check"] == "grim" and f["verdict"] == "FAIL"]
    assert grim_fails, report["summary"]
    assert any("18.72" in str(f["inputs"].get("mean")) for f in grim_fails)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL  {name}: {exc}")
    sys.exit(1 if failures else 0)
