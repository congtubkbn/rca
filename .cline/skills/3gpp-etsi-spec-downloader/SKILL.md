---
name: 3gpp-etsi-spec-downloader
description: Download 3GPP technical specifications from ETSI. Use this when you need to fetch TS PDFs (e.g., TS 38.331, TS 24.229), always get the latest version, and organize them into a local spec library at 3gpp-spec-document/. Supports single TS download, batch operations, version pinning, and manifest tracking.
compatibility: Python 3.8+, Playwright, requests
---

# 3GPP ETSI Spec Downloader

Download and organize 3GPP technical specifications from ETSI into a structured local library.

## When to use

- **User says:** "Download TS 38.331", "Fetch the latest version of TS 24.229", "Get these specs: 38.331, 24.229, 26.114"
- **User is building a spec library** for RCA, protocol analysis, or reference documentation
- **Need latest versions** — this skill always fetches the newest version available on ETSI
- **Want organized storage** — specs stored by series and number with metadata

## How it works

Run this command in your project root (`e:\the.thoi\Project\rca-v6`):

```bash
python .cline/skills/3gpp-etsi-spec-downloader/scripts/etsi_downloader.py <operation> [args]
```

### Operations

**Download single TS:**
```bash
python .cline/skills/3gpp-etsi-spec-downloader/scripts/etsi_downloader.py download --ts 38.331
```

**Download batch (from file):**
```bash
# Create file: specs.txt with one TS per line (38.331, 24.229, 26.114, ...)
python .cline/skills/3gpp-etsi-spec-downloader/scripts/etsi_downloader.py download-batch --file specs.txt
```

**List local specs:**
```bash
python .cline/skills/3gpp-etsi-spec-downloader/scripts/etsi_downloader.py list
```

**Check spec info (without downloading):**
```bash
python .cline/skills/3gpp-etsi-spec-downloader/scripts/etsi_downloader.py info --ts 38.331
```

**Resume failed downloads:**
```bash
python .cline/skills/3gpp-etsi-spec-downloader/scripts/etsi_downloader.py resume
```

### Output Structure

Specs stored in `3gpp-spec-document/` (project root):

```
3gpp-spec-document/
├── 24/
│   ├── 24_229/
│   │   ├── ts_24229_v19_06_00.pdf
│   │   └── manifest.json
│   └── 24_301/
│       ├── ts_24301_v19_06_00.pdf
│       └── manifest.json
├── 36/
│   ├── 36_211/
│   │   ├── ts_36211_v19_02_00.pdf
│   │   └── manifest.json
└── 38/
    ├── 38_331/
    │   ├── ts_38331_v17_03_00.pdf
    │   └── manifest.json
```

Each `manifest.json` tracks:
- TS title and series/number
- Download date (ISO 8601)
- ETSI URL and version info
- File size, MD5 checksum
- Status (complete, failed, pending)

### Manifest Example

```json
{
  "ts_number": "38.331",
  "ts_series": "38",
  "ts_title": "Physical layer procedures (TDD) for NR",
  "version": "17.3.0",
  "release": "REL-17",
  "downloaded_at": "2026-08-16T10:30:45Z",
  "etsi_url": "https://www.etsi.org/deliver/etsi_ts/138300_138399/138331/17.03.00_60/ts_138331v170300p.pdf",
  "file_size_bytes": 5242880,
  "md5_checksum": "abc123...",
  "status": "complete"
}
```

## Script options

- `--ts <number>` — TS to download (e.g., 38.331)
- `--file <path>` — Batch file (one TS per line)
- `--version <v>` — Pin to specific version (e.g., 17.3.0); default: latest
- `--force` — Re-download even if exists locally
- `--quiet` — Suppress progress output
- `--timeout <sec>` — Download timeout (default: 300s)

## Error handling

- **TS not found on ETSI** — reports available versions, suggests alternatives
- **Download fails** — saves partial file to `.pending/`, `resume` command retries
- **Version mismatch** — checks MD5, warns if file corrupted
- **ETSI site changes** — script detects structural changes and fails gracefully

## Return format (JSON)

All operations support `--json` flag for machine parsing:

```bash
python .cline/skills/3gpp-etsi-spec-downloader/scripts/etsi_downloader.py download --ts 38.331 --json
```

Returns:
```json
{
  "success": true,
  "ts": "38.331",
  "version": "17.3.0",
  "local_path": "3gpp-spec-document/38/38_331/ts_38331_v17_03_00.pdf",
  "file_size_bytes": 5242880,
  "download_time_seconds": 23.4,
  "manifest_path": "3gpp-spec-document/38/38_331/manifest.json"
}
```

---

See `references/directory-schema.md` for full folder organization details.
