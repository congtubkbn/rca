# 3GPP Spec Directory Organization

## Folder Structure

```
3gpp-spec-document/              # Project root
├── .pending/                    # Incomplete downloads (for resume)
│   ├── ts_38331_v17_03_00.pdf.pending
│   └── ts_24229_v19_06_00.pdf.pending
├── 24/                          # TS 24.xxx series
│   ├── 24_228/
│   │   ├── ts_24228_v19_06_00.pdf
│   │   └── manifest.json
│   ├── 24_229/
│   │   ├── ts_24229_v19_06_00.pdf
│   │   └── manifest.json
│   └── 24_301/
│       ├── ts_24301_v19_06_00.pdf
│       └── manifest.json
├── 26/                          # TS 26.xxx series
│   └── 26_114/
│       ├── ts_26114_v19_02_00.pdf
│       └── manifest.json
├── 29/                          # TS 29.xxx series
│   ├── 29_061/
│   │   ├── ts_29061_v19_01_00.pdf
│   │   └── manifest.json
│   ├── 29_165/
│   │   ├── ts_29165_v19_00_00.pdf
│   │   └── manifest.json
│   └── 29_281/
│       ├── ts_29281_v19_02_00.pdf
│       └── manifest.json
├── 33/                          # TS 33.xxx series (security)
│   └── 33_501/
│       ├── ts_33501_v19_05_00.pdf
│       └── manifest.json
├── 36/                          # TS 36.xxx series (LTE)
│   ├── 36_211/
│   │   ├── ts_36211_v19_02_00.pdf
│   │   └── manifest.json
│   ├── 36_321/
│   │   ├── ts_36321_v19_01_00.pdf
│   │   └── manifest.json
│   └── 36_331/
│       ├── ts_36331_v19_01_00.pdf
│       └── manifest.json
├── 38/                          # TS 38.xxx series (NR/5G)
│   ├── 38_331/
│   │   ├── ts_38331_v17_03_00.pdf
│   │   └── manifest.json
│   ├── 38_501/
│   │   ├── ts_38501_v17_00_00.pdf
│   │   └── manifest.json
│   └── 38_521/
│       ├── ts_38521_v17_01_00.pdf
│       └── manifest.json
└── 23/                          # TS 23.xxx series (architecture)
    ├── 23_228/
    │   ├── ts_23228_v19_06_00.pdf
    │   └── manifest.json
    └── 23_501/
        ├── ts_23501_v19_05_00.pdf
        └── manifest.json
```

## Naming Conventions

### Folder Names
- **Series folder**: `{SERIES}` (e.g., `24`, `38`, `36`)
  - 2-digit numeric TS series number
- **TS folder**: `{SERIES}_{NUMBER}` (e.g., `24_229`, `38_331`)
  - Uses underscore separator for clarity

### PDF Filenames
- **Format**: `ts_{SERIESNUMBER}_v{VERSION}.pdf`
- **Example**: `ts_38331_v17_03_00.pdf` for TS 38.331 v17.3.0
- **Version format**: Underscores replace dots (17.3.0 → v17_03_00)

### Manifest Filenames
- **Always**: `manifest.json` in the TS folder (same level as PDF)

## Manifest File Structure

Each TS folder contains one `manifest.json` with full metadata:

```json
{
  "ts_number": "38.331",
  "ts_series": "38",
  "ts_title": "Physical layer procedures (TDD) for NR",
  "version": "17.3.0",
  "release": "REL-17",
  "downloaded_at": "2026-08-16T10:30:45.123456+00:00",
  "etsi_url": "https://www.etsi.org/deliver/etsi_ts/138300_138399/138331/17.03.00_60/ts_138331v170300p.pdf",
  "file_size_bytes": 5242880,
  "md5_checksum": "a1b2c3d4e5f6...",
  "status": "complete"
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `ts_number` | string | TS reference (e.g., "38.331") |
| `ts_series` | string | Series number only (e.g., "38") |
| `ts_title` | string | Full TS title from ETSI |
| `version` | string | Version in 3GPP format (e.g., "17.3.0") |
| `release` | string | Release name (e.g., "REL-17", "REL-19") |
| `downloaded_at` | ISO 8601 | UTC download timestamp |
| `etsi_url` | URL | Direct ETSI download URL |
| `file_size_bytes` | integer | PDF size in bytes |
| `md5_checksum` | hex string | MD5 for integrity check |
| `status` | string | `complete`, `pending`, `failed` |

## Version Mapping

3GPP release to TS series version mapping (common):

| Release | TS 24.x | TS 36.x | TS 38.x | TS 23.x |
|---------|---------|---------|---------|---------|
| Rel-15  | 15.x.x  | 15.x.x  | 15.x.x  | 15.x.x  |
| Rel-16  | 16.x.x  | 16.x.x  | 16.x.x  | 16.x.x  |
| Rel-17  | 17.x.x  | 17.x.x  | 17.x.x  | 17.x.x  |
| Rel-18  | 18.x.x  | 18.x.x  | 18.x.x  | 18.x.x  |
| Rel-19  | 19.x.x  | 19.x.x  | 19.x.x  | 19.x.x  |

## Suggested TS Groups

### VoLTE (Protocol & IMS)
- `24_228/` — SIP signaling flows
- `24_229/` — SIP procedures (core)
- `24_292/` — SRVCC fallback
- `26_114/` — Media handling
- `23_228/` — IMS architecture

### LTE (RAN)
- `36_211/` — Physical layer (FDD)
- `36_212/` — Multiplexing (FDD)
- `36_213/` — Physical layer procedures (FDD)
- `36_321/` — MAC
- `36_331/` — RRC

### 5G NR
- `38_201/` — Architecture
- `38_211/` — Physical layer
- `38_213/` — Physical layer procedures
- `38_321/` — MAC
- `38_331/` — RRC

### Core Network (EPC/5GC)
- `23_228/` — IMS architecture
- `23_401/` — GPRS enhancements (EPC)
- `23_501/` — 5GC architecture
- `29_061/` — GTP
- `29_281/` — GTPv2

### Security
- `33_501/` — Security (5G)

## Index File (Optional)

Create `3gpp-spec-document/INDEX.md` to manually maintain a reading guide:

```markdown
# 3GPP Specification Library Index

## Core VoLTE Reading Path
1. 23.228 (IMS architecture) — Start here
2. 24.229 (SIP call procedures)
3. 24.292 (CS fallback / SRVCC)
4. 26.114 (Media and RTP)

## LTE Air Interface
1. 36.211 (Physical layer concepts)
2. 36.212 (Multiplexing)
3. 36.213 (Physical layer procedures)

## 5G NR Air Interface
1. 38.201 (Architecture intro)
2. 38.211 (Physical layer)
3. 38.213 (Procedures)

[... more sections ...]
```

## Maintenance

### Removing Old Versions
When a new version is available, old PDFs can be deleted:

```bash
# Keep only manifest, remove old PDF
rm 3gpp-spec-document/38/38_331/ts_38331_v16_*.pdf
```

The manifest stays for historical reference.

### Checking Integrity
Verify downloaded files:

```bash
# Manual check
md5sum 3gpp-spec-document/38/38_331/ts_38331_v17_03_00.pdf
# Compare against manifest.json's md5_checksum field
```

### Synchronizing Across Machines
Manifest files are lightweight JSON — commit them to Git. PDFs can be in `.gitignore`:

```
# .gitignore
3gpp-spec-document/**/*.pdf
3gpp-spec-document/.pending/
```

Then share manifests to sync download references across team.
