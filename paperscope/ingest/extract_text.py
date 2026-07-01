"""PDF text extraction using PyMuPDF."""

from pathlib import Path
from typing import Optional


def extract_text(pdf_path: Path, output_path: Optional[Path] = None) -> str:
    """Extract text from a PDF file.

    Args:
        pdf_path: Path to the PDF file
        output_path: Optional path to save extracted text

    Returns:
        Extracted text as string
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("'PyMuPDF' package required. Install with: pip install PyMuPDF")

    doc = fitz.open(str(pdf_path))

    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        if text.strip():
            pages.append(f"--- Page {page_num + 1} ---\n{text}")

    doc.close()

    full_text = "\n\n".join(pages)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_text)

    return full_text


def extract_batch(
    pdf_dir: Path,
    text_dir: Path,
    verbose: bool = True,
) -> int:
    """Extract text from all PDFs in a directory.

    Args:
        pdf_dir: Directory containing PDF files
        text_dir: Directory to save extracted text files
        verbose: Print progress

    Returns:
        Number of files processed
    """
    text_dir.mkdir(parents=True, exist_ok=True)
    processed = 0

    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        text_path = text_dir / f"{pdf_path.stem}.txt"

        if text_path.exists():
            continue

        try:
            extract_text(pdf_path, text_path)
            processed += 1
            if verbose:
                print(f"  Extracted: {pdf_path.name}")
        except Exception as e:
            if verbose:
                print(f"  Failed: {pdf_path.name}: {e}")

    if verbose:
        print(f"\n  Processed {processed} PDFs")

    return processed
