# Playbook Promotion Reference

This reference specifies the engineer-initiated playbook promotion workflow for `rca-learn`.
Unlike writing case records into `.rca/knowledge/cases/<case_id>.json`, playbook promotion is an explicit, separate action that generalizes repeated patterns across one or more case records into reviewed Markdown prose.

Promoted playbooks written to `.rca/knowledge/playbooks/<playbook_id>.md` are the **sole part of `.rca/` committed to git** (see `.gitignore` carve-out). Staging drafts live in `.rca/knowledge/.drafts/<playbook_id>.md` and remain git-ignored.

> [!NOTE]
> This is a **different concept** from `scope.json.classification.matched_playbook`, which names a row in `rca-scope`'s hand-maintained `references/known-issue-types.md`. Promoting a playbook here never modifies `known-issue-types.md`.

---

## 1. `promote` — Draft a Playbook

**Invocation forms**:
- `promote <playbook_id> from <case_id>[, <case_id>...]`
- `promote <playbook_id> for issue_type <type>`

### Step 1: Parse arguments

Parse `playbook_id` (a short slug, e.g. `qc9205_ims_timeout`) and either:
- An explicit list of `case_id`s (e.g. `PLM-12345-run-01`, `PLM-19090-run-02`), or
- An `issue_type` to match (e.g. `sms_failure`).

If neither is present, HALT:
`"promote needs at least one existing case to draft from — name case_id(s) (e.g. promote qc9205_ims_timeout from PLM-12345-run-01, PLM-19090-run-02) or an issue_type to match across all recorded cases (e.g. promote generic_sms_cp_error for issue_type sms_failure)."`

### Step 2: Resolve source cases

- **Explicit `case_id`s**: Read each `.rca/knowledge/cases/<case_id>.json`. If any named case file does not exist, HALT naming exactly which one(s) are missing — never silently drop a case the engineer named.
- **`issue_type` matching**: Read all files matching `.rca/knowledge/cases/*.json` and keep those whose `issue_type` matches. If none match, HALT:
  `"No recorded cases for issue_type '<type>' yet — nothing to draft a playbook from."`

### Step 3: Synthesize playbook draft

Draft the playbook body in Markdown per `_shared/run-bundle-layout.md`:

```markdown
# Playbook: <short title, e.g. "VoLTE call drop — Qualcomm 9205, IMS re-INVITE timeout">

Promoted: <ISO 8601 now> — drafted from <case_id, case_id, ...>

<engineer-reviewed prose: the pattern, the issue type(s) it applies to,
what to check first, and any chip-series-specific vendor-documentation
caveat this pattern has confirmed repeatedly>
```

1. **Title**: A short, descriptive name summarizing the pattern across all source cases (not copied verbatim from any single case's `symptom`).
2. **Provenance line**: `Promoted: <ISO 8601 now> — drafted from <case_id, case_id, ...>` listing every source case ID.
3. **Core body**:
   - The common `issue_type`(s).
   - Shared shape of `failure_point` and `root_cause` across source cases, preserving the exact tiers carried in the source cases (e.g., if a source case carries `ASSUMED` or `CODE_UNAVAILABLE`, state so plainly — never smooth into false certainty).
   - What a future engineer should check first when encountering this pattern.
   - **Contradicted vendor documentation**: Every `contradicted_docs` entry shared across two or more source cases (same `document`, same `chip_series`) must be written up explicitly.
4. **Single-case disclaimer**: If drafted from only one case, include an explicit note:
   `"Drafted from a single observed instance; not yet a confirmed repeated pattern."` (Promotion is not blocked on case count, but single-case origin must be stated transparently).

### Step 4: Write staging draft

Create `.rca/knowledge/.drafts/` if needed. Write the draft to `.rca/knowledge/.drafts/<playbook_id>.md`.
If a draft already exists at this path, overwrite it.

### Step 5: Report and HALT

Display the full draft to the engineer and explain:
- Reply `confirm playbook <playbook_id>` to run the customer-data check and promote to `.rca/knowledge/playbooks/<playbook_id>.md`.
- Reply `discard playbook <playbook_id>` to drop the draft without saving.
- HALT.

---

## 2. `confirm playbook <playbook_id>`

**Invocation form**: `confirm playbook <playbook_id>`

### Step 1: Verify draft exists

If `.rca/knowledge/.drafts/<playbook_id>.md` does not exist, HALT:
`"No standing draft named '<playbook_id>' — run promote first."`

### Step 2: Guard against overwriting confirmed playbooks

If `.rca/knowledge/playbooks/<playbook_id>.md` already exists, HALT:
`"A playbook named '<playbook_id>' already exists — promoted playbooks are never overwritten from here. Pick a different id, or edit knowledge/playbooks/<playbook_id>.md directly; it is a plain, engineer-owned Markdown file once written."`

### Step 3: Run the Customer-Data Check

Execute the full two-layer Customer-Data Check (Section 4 below) on `.rca/knowledge/.drafts/<playbook_id>.md`.

If any violation is detected:
- **Do not write to `knowledge/playbooks/`**.
- HALT, reporting the matching pattern and location.
- Inform the engineer that the draft remains at `.rca/knowledge/.drafts/<playbook_id>.md` for manual editing and re-confirmation.

### Step 4: Promote to committed playbooks

If the draft passes the customer-data check cleanly:
1. Create `.rca/knowledge/playbooks/` if it does not exist.
2. Write draft content verbatim to `.rca/knowledge/playbooks/<playbook_id>.md`.
3. Delete staging draft `.rca/knowledge/.drafts/<playbook_id>.md`.
4. Report: Playbook successfully promoted to `.rca/knowledge/playbooks/<playbook_id>.md`. Remind the engineer that adding and committing this file to git is their own explicit action (`git add` / `git commit`).
5. HALT.

---

## 3. `discard playbook <playbook_id>`

**Invocation form**: `discard playbook <playbook_id>`

1. Delete `.rca/knowledge/.drafts/<playbook_id>.md` if it exists (report as a no-op if absent).
2. Never touch `.rca/knowledge/playbooks/<playbook_id>.md` even if a file with the same name exists there.
3. Report that the draft was discarded.
4. HALT.

---

## 4. The Customer-Data Check

Every playbook draft must pass both layers before being written to `.rca/knowledge/playbooks/`:

### Layer 1: Mechanical pattern scan

Any match immediately blocks promotion:

1. **Subscriber / Hardware IDs**: A sequence of 10 or more consecutive digits (`\b\d{10,}\b`) anywhere outside the `case_id`s in the provenance line (catches IMSI, IMEI, MSISDN, ICCID).
2. **Email addresses**: Any email address pattern (`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`).
3. **Customer issue identifiers**: Any `PLM-<digits>` reference appearing anywhere outside the required `case_id`s in the provenance header (`Promoted: ... drafted from ...`).
4. **Raw log dumps**: Any block of two or more lines reproducing literal log formatting (timestamped, bracketed, or pipe-delimited fields) rather than plain-English descriptions.

### Layer 2: Contextual judgment read

Examine the draft for customer-identifying information:
- Subscriber phone numbers, device serial numbers, operator account numbers, or personal names originating from PLM tickets.
- **Rule**: If in doubt, reject and ask the engineer to rephrase. A false positive costs only a minor edit; a false negative risks committing proprietary customer data to git.
