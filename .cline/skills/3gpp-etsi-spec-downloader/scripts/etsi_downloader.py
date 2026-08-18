#!/usr/bin/env python3
"""
ETSI 3GPP Technical Specification Downloader

Downloads and organizes 3GPP TS specs from ETSI.org into a structured local library.
Handles version tracking, resume, and manifest generation.
"""

import argparse
import asyncio
import json
import os
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import sys

# Try imports, with helpful error messages
try:
    import aiohttp
except ImportError:
    print("ERROR: aiohttp not installed. Run: pip install aiohttp", file=sys.stderr)
    sys.exit(1)

try:
    from playwright.async_api import async_playwright, Page
except ImportError:
    print("ERROR: Playwright not installed. Run: pip install playwright && playwright install", file=sys.stderr)
    sys.exit(1)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
SPEC_DIR = PROJECT_ROOT / "3gpp-spec-document"
PENDING_DIR = SPEC_DIR / ".pending"


class ETSIDownloader:
    def __init__(self, quiet=False, timeout=300):
        self.quiet = quiet
        self.timeout = timeout
        self.ETSI_BASE = "https://www.etsi.org/standards"

    def log(self, msg: str):
        if not self.quiet:
            print(msg)

    async def search_ts(self, ts_number: str, browser) -> Dict:
        """Search ETSI for TS and extract available versions."""
        page = await browser.new_page()
        try:
            search_url = f"{self.ETSI_BASE}/#page=1&search={ts_number}&title=1&etsiNumber=0&content=0&version=1&onApproval=0&published=1&withdrawn=0&historical=0&isCurrent=1&superseded=1"
            self.log(f"Searching ETSI for TS {ts_number}...")
            await page.goto(search_url, wait_until="networkidle", timeout=self.timeout * 1000)

            # Wait for results to load
            await page.wait_for_selector("table tbody tr", timeout=10000)

            # Extract first matching result (most recent)
            rows = await page.query_selector_all("table tbody tr")
            if not rows:
                return {"found": False, "ts": ts_number, "error": "No results on ETSI"}

            # Click first result to get details
            first_row = rows[0]
            await first_row.click()
            await page.wait_for_load_state("networkidle")

            # Parse TS info
            title_elem = await page.query_selector("h1")
            title = await title_elem.text_content() if title_elem else ""

            # Extract version from PDF filename in URL (most reliable source)
            pdf_link = await page.get_attribute('a[href$=".pdf"]', 'href') if await page.query_selector('a[href$=".pdf"]') else None

            version = "unknown"
            if pdf_link:
                # Extract version from URL like: ts_138331v170300p.pdf -> 17.3.0
                match = re.search(r'v(\d{2})(\d{2})(\d{2})', pdf_link)
                if match:
                    major, minor, patch = match.groups()
                    version = f"{int(major)}.{int(minor)}.{int(patch)}"
                else:
                    # Fallback: try to find version in page text
                    version_texts = await page.query_selector_all("text")
                    for elem in version_texts:
                        text = await elem.text_content()
                        if text and re.search(r'\d+\.\d+\.\d+', text):
                            match = re.search(r'(\d+\.\d+\.\d+)', text)
                            if match:
                                version = match.group(1)
                                break

            if not pdf_link:
                return {"found": False, "ts": ts_number, "error": "No PDF link found"}

            # Build absolute URL
            if not pdf_link.startswith('http'):
                pdf_link = f"https://www.etsi.org{pdf_link}"

            return {
                "found": True,
                "ts": ts_number,
                "title": title.strip(),
                "version": version,
                "url": pdf_link,
                "release": self._extract_release(version)
            }
        finally:
            await page.close()

    def _extract_release(self, version: str) -> str:
        """Map version to 3GPP release (e.g., 17.x.x -> REL-17)."""
        match = re.match(r'(\d+)', version)
        if match:
            return f"REL-{match.group(1)}"
        return "UNKNOWN"

    async def download_pdf(self, url: str, dest_path: Path) -> Tuple[bool, int, str]:
        """Download PDF and return (success, filesize, md5)."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = dest_path.with_suffix('.tmp')

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                    if resp.status != 200:
                        return False, 0, ""

                    md5 = hashlib.md5()
                    size = 0
                    with open(temp_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)
                            md5.update(chunk)
                            size += len(chunk)

                    temp_path.rename(dest_path)
                    return True, size, md5.hexdigest()
        except Exception as e:
            self.log(f"Download error: {e}")
            if temp_path.exists():
                temp_path.rename(dest_path.with_suffix('.pending'))
            return False, 0, ""

    def _parse_ts_number(self, ts_str: str) -> Tuple[str, str]:
        """Parse TS number into (series, number). E.g., '38.331' -> ('38', '331')."""
        match = re.match(r'(\d+)\.(\d+)', ts_str)
        if match:
            return match.group(1), match.group(2)
        raise ValueError(f"Invalid TS format: {ts_str}")

    def _get_spec_path(self, ts_number: str) -> Path:
        """Return target folder for TS."""
        series, number = self._parse_ts_number(ts_number)
        return SPEC_DIR / series / f"{series}_{number}"

    def _get_manifest_path(self, ts_number: str) -> Path:
        """Return manifest.json path for TS."""
        return self._get_spec_path(ts_number) / "manifest.json"

    def _make_filename(self, ts_number: str, version: str) -> str:
        """Create filename from TS and version in ETSI format. E.g., ts_136211v190200p.pdf"""
        series, number = self._parse_ts_number(ts_number)
        # ETSI format: ts_<seriesnumber>v<versioncompact>p.pdf
        # E.g., ts_136211v190200p.pdf for TS 36.211 v19.2.00
        version_compact = version.replace('.', '').ljust(6, '0')  # 19.2.0 → 190200
        return f"ts_{series}{number}v{version_compact}p.pdf"

    async def download_ts(self, ts_number: str, version: Optional[str] = None, force: bool = False) -> Dict:
        """Download single TS."""
        SPEC_DIR.mkdir(exist_ok=True)
        PENDING_DIR.mkdir(exist_ok=True)

        spec_path = self._get_spec_path(ts_number)
        manifest_path = self._get_manifest_path(ts_number)

        # Check if already exists (unless forced)
        if manifest_path.exists() and not force:
            with open(manifest_path) as f:
                existing = json.load(f)
                self.log(f"TS {ts_number} v{existing['version']} already downloaded")
                return {
                    "success": True,
                    "status": "already_exists",
                    "ts": ts_number,
                    "version": existing["version"],
                    "local_path": str(spec_path / self._make_filename(ts_number, existing["version"]))
                }

        # Search ETSI
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            result = await self.search_ts(ts_number, browser)
            await browser.close()

        if not result.get("found"):
            return {"success": False, "ts": ts_number, "error": result.get("error", "Not found")}

        url = result["url"]
        version = version or result["version"]

        # Download
        filename = self._make_filename(ts_number, version)
        file_path = spec_path / filename
        spec_path.mkdir(parents=True, exist_ok=True)

        self.log(f"Downloading {ts_number} v{version}...")
        success, file_size, md5 = await self.download_pdf(url, file_path)

        if not success:
            return {
                "success": False,
                "ts": ts_number,
                "error": "Download failed",
                "pending_file": str(file_path.with_suffix('.pending'))
            }

        # Create manifest
        manifest = {
            "ts_number": ts_number,
            "ts_series": self._parse_ts_number(ts_number)[0],
            "ts_title": result.get("title", ""),
            "version": version,
            "release": result.get("release", "UNKNOWN"),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "etsi_url": url,
            "file_size_bytes": file_size,
            "md5_checksum": md5,
            "status": "complete"
        }

        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

        self.log(f"✓ {ts_number} v{version} saved to {file_path.relative_to(PROJECT_ROOT)}")

        return {
            "success": True,
            "ts": ts_number,
            "version": version,
            "local_path": str(file_path.relative_to(PROJECT_ROOT)),
            "file_size_bytes": file_size,
            "manifest_path": str(manifest_path.relative_to(PROJECT_ROOT))
        }

    async def download_batch(self, ts_list: List[str]) -> List[Dict]:
        """Download multiple TSs."""
        results = []
        for ts in ts_list:
            result = await self.download_ts(ts.strip())
            results.append(result)
        return results

    def list_local_specs(self) -> Dict:
        """List all locally downloaded specs."""
        specs = []
        if not SPEC_DIR.exists():
            return {"count": 0, "specs": []}

        for manifest_path in SPEC_DIR.glob("*/*/manifest.json"):
            with open(manifest_path) as f:
                manifest = json.load(f)
                specs.append({
                    "ts": manifest["ts_number"],
                    "version": manifest["version"],
                    "release": manifest.get("release", ""),
                    "downloaded": manifest["downloaded_at"],
                    "path": str(manifest_path.parent.relative_to(SPEC_DIR))
                })

        specs.sort(key=lambda x: x["ts"])
        return {"count": len(specs), "specs": specs}

    async def check_spec_info(self, ts_number: str) -> Dict:
        """Get spec info from ETSI without downloading."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            result = await self.search_ts(ts_number, browser)
            await browser.close()
        return result

    def resume_downloads(self) -> Dict:
        """Resume incomplete downloads from .pending folder."""
        if not PENDING_DIR.exists():
            return {"count": 0, "resumed": []}

        pending_files = list(PENDING_DIR.glob("**/*.pending"))
        self.log(f"Found {len(pending_files)} pending downloads")

        # Note: Full resume logic would require re-parsing which TS each file belongs to
        # For now, return list of pending files
        return {
            "count": len(pending_files),
            "pending_files": [str(f.relative_to(PROJECT_ROOT)) for f in pending_files]
        }


async def main():
    parser = argparse.ArgumentParser(
        description="Download and manage 3GPP specs from ETSI"
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress output")
    parser.add_argument("--timeout", type=int, default=300, help="Download timeout (seconds)")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    subparsers = parser.add_subparsers(dest="command")

    # download
    download_parser = subparsers.add_parser("download", help="Download single TS")
    download_parser.add_argument("--ts", required=True, help="TS number (e.g., 38.331)")
    download_parser.add_argument("--version", help="Specific version (default: latest)")
    download_parser.add_argument("--force", action="store_true", help="Re-download if exists")

    # download-batch
    batch_parser = subparsers.add_parser("download-batch", help="Download multiple TSs")
    batch_parser.add_argument("--file", required=True, help="File with TS list (one per line)")

    # list
    subparsers.add_parser("list", help="List downloaded specs")

    # info
    info_parser = subparsers.add_parser("info", help="Check spec info without downloading")
    info_parser.add_argument("--ts", required=True, help="TS number")

    # resume
    subparsers.add_parser("resume", help="Resume failed downloads")

    args = parser.parse_args()

    downloader = ETSIDownloader(quiet=args.quiet, timeout=args.timeout)
    result = None

    try:
        if args.command == "download":
            result = await downloader.download_ts(
                args.ts,
                version=args.version,
                force=args.force
            )
        elif args.command == "download-batch":
            with open(args.file) as f:
                ts_list = [line.strip() for line in f if line.strip()]
            result = await downloader.download_batch(ts_list)
        elif args.command == "list":
            result = downloader.list_local_specs()
        elif args.command == "info":
            result = await downloader.check_spec_info(args.ts)
        elif args.command == "resume":
            result = downloader.resume_downloads()
        else:
            parser.print_help()
            sys.exit(1)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if isinstance(result, dict) and "success" in result:
                if result["success"]:
                    downloader.log(f"Result: {json.dumps(result, indent=2)}")
                else:
                    downloader.log(f"Error: {result.get('error', 'Unknown')}")
            else:
                print(json.dumps(result, indent=2))

    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        if args.json:
            print(json.dumps(error_result, indent=2))
        else:
            downloader.log(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
