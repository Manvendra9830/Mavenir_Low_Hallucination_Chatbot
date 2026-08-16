"""
TeleRAG — 3GPP Archive Inspector

Inspects ZIP contents to identify the authoritative specification document.
Per user requirement: does NOT blindly prefer DOCX over PDF.
Instead inspects all files, identifies the actual spec, and selects the format
that gives the most reliable extraction with page/section preservation.
"""
import logging
import re
import zipfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# File patterns to SKIP (auxiliary/template/readme)
SKIP_PATTERNS = [
    r"^__MACOSX",
    r"\.DS_Store$",
    r"Thumbs\.db$",
    r"README",
    r"CHANGES",
    r"template",
    r"^~\$",          # Word temp files
    r"\.tmp$",
    r"\.bak$",
]

# Supported document formats for extraction
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc"}


def _is_auxiliary_file(name: str) -> bool:
    """Check if a file is auxiliary (not the spec document)."""
    basename = Path(name).name
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, basename, re.IGNORECASE):
            return True
    return False


def _extract_spec_number_from_filename(filename: str) -> Optional[str]:
    """Try to extract a spec number like '23501' from a filename."""
    match = re.search(r"(\d{5})", filename)
    return match.group(1) if match else None


def inspect_archive(zip_path: Path, expected_spec_number: str) -> dict:
    """Inspect a 3GPP ZIP archive and identify the authoritative spec document.
    
    Strategy:
    1. List all files in the archive.
    2. Filter out auxiliary/template/readme files.
    3. Among supported doc formats, identify the one that matches the spec number.
    4. Prefer PDF for extraction reliability (page numbers, section structure).
       - PDF preserves page boundaries natively.
       - DOCX has no inherent page concept — page breaks are approximate.
    5. If only DOCX is available, use it (still better than nothing).
    6. If multiple candidates exist, pick the largest one (most complete).
    
    Returns dict with:
        - selected_file: the filename inside the ZIP to extract
        - selected_format: 'pdf' or 'docx'
        - all_files: list of all files in the archive
        - candidates: list of candidate spec documents
        - reason: why this file was selected
    """
    expected_num_clean = expected_spec_number.replace(".", "").replace(" ", "")

    result = {
        "zip_path": str(zip_path),
        "expected_spec": expected_spec_number,
        "selected_file": None,
        "selected_format": None,
        "all_files": [],
        "candidates": [],
        "reason": None,
    }

    if not zip_path.exists():
        result["reason"] = "ZIP file does not exist"
        return result

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            all_entries = zf.namelist()
            result["all_files"] = all_entries

            # Filter to supported document files, skip auxiliaries
            candidates = []
            for entry in all_entries:
                if _is_auxiliary_file(entry):
                    continue
                ext = Path(entry).suffix.lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                info = zf.getinfo(entry)
                spec_num = _extract_spec_number_from_filename(entry)

                candidates.append({
                    "filename": entry,
                    "extension": ext,
                    "size_bytes": info.file_size,
                    "spec_number_match": spec_num == expected_num_clean if spec_num else False,
                    "extracted_spec_num": spec_num,
                })

            result["candidates"] = candidates

            if not candidates:
                result["reason"] = "No supported document files found in archive"
                return result

            # Step 1: Filter to files that match the expected spec number
            matching = [c for c in candidates if c["spec_number_match"]]
            pool = matching if matching else candidates

            # Step 2: Separate by format
            pdfs = [c for c in pool if c["extension"] == ".pdf"]
            docxs = [c for c in pool if c["extension"] == ".docx"]
            docs = [c for c in pool if c["extension"] == ".doc"]

            # Step 3: Prefer PDF for page/section fidelity
            # PDF gives us reliable page numbers, section headers are extractable,
            # and the format is stable for 3GPP specs.
            if pdfs:
                selected = max(pdfs, key=lambda c: c["size_bytes"])
                result["selected_file"] = selected["filename"]
                result["selected_format"] = "pdf"
                result["reason"] = (
                    "Selected PDF — provides reliable page numbers and section structure "
                    "for extraction. Largest PDF matching spec number."
                )
            elif docxs:
                selected = max(docxs, key=lambda c: c["size_bytes"])
                result["selected_file"] = selected["filename"]
                result["selected_format"] = "docx"
                result["reason"] = (
                    "No PDF found. Selected DOCX — structured content available but "
                    "page numbers will be approximate."
                )
            elif docs:
                selected = max(docs, key=lambda c: c["size_bytes"])
                result["selected_file"] = selected["filename"]
                result["selected_format"] = "doc"
                result["reason"] = (
                    "Only legacy .doc format available. Will attempt extraction but "
                    "fidelity may be reduced."
                )
            else:
                result["reason"] = "No suitable document format found"
                return result

            logger.info(
                f"Archive {zip_path.name}: selected '{result['selected_file']}' "
                f"({result['selected_format']}) — {result['reason']}"
            )

    except zipfile.BadZipFile:
        result["reason"] = "Invalid/corrupt ZIP file"
        logger.error(f"Bad ZIP file: {zip_path}")
    except Exception as e:
        result["reason"] = f"Error inspecting archive: {e}"
        logger.error(f"Error inspecting {zip_path}: {e}")

    return result


def extract_selected_file(zip_path: Path, selected_file: str, output_dir: Path) -> Optional[Path]:
    """Extract only the selected authoritative document from the archive.
    
    Preserves the original archive. Returns path to extracted file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / Path(selected_file).name

    if output_path.exists():
        logger.info(f"Already extracted: {output_path.name}")
        return output_path

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            data = zf.read(selected_file)
            output_path.write_bytes(data)
            logger.info(f"Extracted: {selected_file} -> {output_path}")
            return output_path
    except Exception as e:
        logger.error(f"Failed to extract {selected_file}: {e}")
        return None
