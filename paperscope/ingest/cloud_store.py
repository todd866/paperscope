"""Cloud storage for PDFs via Backblaze B2."""

import json
import os
from pathlib import Path
from typing import Dict, Optional


def get_b2_bucket(bucket_name: str = "paperscope-pdfs"):
    """Get a B2 bucket handle.

    Requires B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY env vars.
    """
    try:
        from b2sdk.v2 import InMemoryAccountInfo, B2Api
    except ImportError:
        raise ImportError("'b2sdk' package required. Install with: pip install b2sdk")

    key_id = os.environ.get("B2_APPLICATION_KEY_ID")
    key = os.environ.get("B2_APPLICATION_KEY")

    if not key_id or not key:
        raise RuntimeError(
            "B2 credentials required. Set B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY env vars."
        )

    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account("production", key_id, key)

    return b2_api.get_bucket_by_name(bucket_name)


def upload_pdf(
    local_path: Path,
    cite_key: str,
    bucket=None,
    bucket_name: str = "paperscope-pdfs",
) -> str:
    """Upload a PDF to B2.

    Returns the B2 file ID.
    """
    if bucket is None:
        bucket = get_b2_bucket(bucket_name)

    remote_name = f"{cite_key}.pdf"

    file_info = bucket.upload_local_file(
        local_file=str(local_path),
        file_name=remote_name,
    )

    return file_info.id_


def download_pdf(
    cite_key: str,
    output_path: Path,
    bucket=None,
    bucket_name: str = "paperscope-pdfs",
) -> Path:
    """Download a PDF from B2."""
    if bucket is None:
        bucket = get_b2_bucket(bucket_name)

    remote_name = f"{cite_key}.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    download_dest = bucket.download_file_by_name(remote_name)
    download_dest.save_to(str(output_path))

    return output_path


def update_manifest(
    manifest_path: Path,
    cite_key: str,
    file_id: str,
    doi: str = "",
) -> None:
    """Update the PDF manifest tracking what's in B2."""
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
    else:
        manifest = {"pdfs": {}}

    manifest["pdfs"][cite_key] = {
        "file_id": file_id,
        "doi": doi,
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
