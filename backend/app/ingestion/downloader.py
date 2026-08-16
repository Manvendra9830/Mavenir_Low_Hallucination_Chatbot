"""
TeleRAG — 3GPP Archive Downloader

Downloads specific Release 18 baseline archives from official 3GPP FTP.
Only downloads the exact version requested — never crawls the full archive.
"""
import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 3GPP version letter mapping:  Release 15='f', 16='g', 17='h', 18='i', 19='j'
RELEASE_LETTER_MAP = {
    "15": "f", "16": "g", "17": "h", "18": "i", "19": "j", "20": "k",
}

# Target specifications with titles
SPEC_CATALOG = {
    "TS 23.501": {"title": "System Architecture for the 5G System (5GS)", "series": "23_series", "number": "23.501"},
    "TS 23.502": {"title": "Procedures for the 5G System (5GS)", "series": "23_series", "number": "23.502"},
    "TS 23.503": {"title": "Policy and Charging Control Framework for the 5G System", "series": "23_series", "number": "23.503"},
    "TS 24.501": {"title": "Non-Access-Stratum (NAS) protocol for 5G System (5GS)", "series": "24_series", "number": "24.501"},
    "TS 38.300": {"title": "NR and NG-RAN Overall Description", "series": "38_series", "number": "38.300"},
    "TS 38.331": {"title": "NR Radio Resource Control (RRC) Protocol Specification", "series": "38_series", "number": "38.331"},
}

# Corpus tiers
TIERS = {
    "FULL": ["TS 23.501", "TS 23.502", "TS 23.503", "TS 24.501", "TS 38.300", "TS 38.331"],
    "CORE": ["TS 23.501", "TS 23.502", "TS 38.300", "TS 38.331"],
    "MINIMAL": ["TS 23.501", "TS 23.502"],
}


def get_archive_filename(spec_number: str, release: str, sub_version: str = "00") -> str:
    """Build the 3GPP archive filename for a spec/release.
    
    E.g. spec_number='23.501', release='18' -> '23501-i00.zip'
    """
    letter = RELEASE_LETTER_MAP.get(release)
    if not letter:
        raise ValueError(f"Unsupported release: {release}")
    num = spec_number.replace(".", "")
    return f"{num}-{letter}{sub_version}.zip"


def get_or_register_spec(spec_key: str) -> dict:
    """Get spec info from catalog, or dynamically register it if it matches TS XX.YYY."""
    if spec_key in SPEC_CATALOG:
        return SPEC_CATALOG[spec_key]
        
    # Attempt to dynamically parse, e.g., "TS 29.500"
    if spec_key.startswith("TS ") and "." in spec_key:
        number = spec_key.replace("TS ", "").strip()
        series_num = number.split(".")[0]
        if series_num.isdigit():
            info = {
                "title": f"3GPP {spec_key}",
                "series": f"{series_num}_series",
                "number": number
            }
            SPEC_CATALOG[spec_key] = info
            return info
            
    raise ValueError(f"Unknown or invalid specification format: {spec_key}")


def get_download_url(spec_number: str, release: str, sub_version: str = "00") -> str:
    """Build the official 3GPP download URL."""
    spec_info = None
    for key, info in SPEC_CATALOG.items():
        if info["number"] == spec_number:
            spec_info = info
            break
            
    if not spec_info:
        # If we just have the number, e.g. '29.500', reconstruct key
        spec_info = get_or_register_spec(f"TS {spec_number}")

    filename = get_archive_filename(spec_number, release, sub_version)
    return f"https://www.3gpp.org/ftp/Specs/archive/{spec_info['series']}/{spec_number}/{filename}"


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            sha256.update(block)
    return sha256.hexdigest()


def download_spec(
    spec_key: str,
    release: str,
    output_dir: Path,
    timeout: float = 120.0,
) -> Optional[dict]:
    """Download a single 3GPP specification archive.
    
    Returns a dict with download metadata, or None on failure.
    """
    try:
        info = get_or_register_spec(spec_key)
    except ValueError as e:
        logger.error(str(e))
        return None

    spec_number = info["number"]
    filename = get_archive_filename(spec_number, release)
    url = get_download_url(spec_number, release)

    spec_dir = output_dir / spec_key.replace(" ", "_")
    spec_dir.mkdir(parents=True, exist_ok=True)
    filepath = spec_dir / filename

    # Skip if already downloaded
    if filepath.exists() and filepath.stat().st_size > 0:
        logger.info(f"Already downloaded: {filename}")
        return {
            "specification": spec_key,
            "version": f"{release}.0.0",
            "release": release,
            "source_filename": filename,
            "source_url": url,
            "local_path": str(filepath),
            "sha256": compute_sha256(filepath),
            "download_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "downloaded",
            "skipped": True,
        }

    logger.info(f"Downloading {spec_key} from {url}")
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

        filepath.write_bytes(response.content)
        sha256 = compute_sha256(filepath)
        logger.info(f"Downloaded {filename} ({filepath.stat().st_size / 1024:.1f} KB)")

        return {
            "specification": spec_key,
            "title": info["title"],
            "version": f"{release}.0.0",
            "release": release,
            "source_filename": filename,
            "source_url": url,
            "local_path": str(filepath),
            "sha256": sha256,
            "download_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "file_size_bytes": filepath.stat().st_size,
            "status": "downloaded",
            "skipped": False,
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error downloading {spec_key}: {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Failed to download {spec_key}: {e}")
        return None


def download_corpus(
    release: str,
    tier: str,
    output_dir: Path,
) -> list[dict]:
    """Download all specs for a given release and tier."""
    specs = TIERS.get(tier, TIERS["FULL"])
    logger.info(f"Downloading corpus: Release {release}, Tier {tier}, Specs: {len(specs)}")

    results = []
    for spec_key in specs:
        result = download_spec(spec_key, release, output_dir)
        if result:
            results.append(result)
        else:
            logger.warning(f"Failed to download {spec_key} — continuing with remaining specs")

    logger.info(f"Downloaded {len(results)}/{len(specs)} specifications")
    return results
