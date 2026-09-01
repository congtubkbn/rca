# Code-Graph Invocation Contract

This documents what `rca-analyze` (issue #8) needs to call the tree-sitter
code-graph capability. Like the log-query capability
(`log-query-invocation.md`) and the PLM MCP connection, it is a
**workspace dependency, not part of this repository** (issue #5,
"capabilities already exist as separate skills"). It is expected to
already be configured in the environment a skill runs in; no skill in
this suite attempts to configure or discover it.

## What it is

A semantic search and call-graph tool over the UE source tree at
`input/log-pointers.json.source_checkout`, pinned to
`input/log-pointers.json.source_commit` — the build that actually produced
this issue's log. It answers "what module implements this", "what does
this function call", "what log macro literals does this path emit" — not
"is this correct", which stays this suite's job, not the capability's.

## Invoking it

```
Call the code-graph capability with:
  source_checkout: <input/log-pointers.json.source_checkout>
  source_commit:   <input/log-pointers.json.source_commit>
  target:          <a module/procedure name, a function symbol, or a log
                     literal to locate the emitting call site for>
  operation:       bind_module | find_implementation | trace_call_path
```

- `source_checkout`/`source_commit` come only from `input/log-pointers.json`
  — never guessed or defaulted to a workspace convention a skill hasn't
  actually checked. If either is `null`, this rung of the ladder cannot
  run at all for this issue; see "When source is unavailable" below —
  this is expected and routine, not an error to work around.
- `target` may originate from any source per `keyword-provenance.md`
  (HARD, SOFT, or a guess) — the capability call itself does not care
  where it came from; what matters is what `rca-analyze` is allowed to do
  with the result afterward, which `keyword-provenance.md` governs.
- `operation` selects what kind of answer is wanted:
  - `bind_module` — which source module implements a named
    procedure/phase.
  - `find_implementation` — where a named function or log literal is
    defined or emitted.
  - `trace_call_path` — the call chain between two named symbols, for
    testing a hypothesis about how one condition leads to another.

## What it returns

```json
{
  "target": "<what was asked for>",
  "operation": "<as invoked>",
  "resolved": true,
  "module": "<module/file path>",
  "symbols": [{"name": "<function/symbol>", "location": "<file:line>"}],
  "is_lib": false
}
```

- `resolved: false` with `is_lib: true` means the module exists but ships
  as a prebuilt lib with no source in this checkout — see below.
- `resolved: false` with `is_lib: false` means the target genuinely was
  not found — record this as a miss per `keyword-provenance.md`'s
  "guessing may ask, never answer": no claim, positive or negative, may
  be drawn from it.

## What the calling skill must do with the result

Same discipline as `log-query-invocation.md`:

1. Write the full returned payload to
   `runs/run-NN/raw/rca-analyze-q-<NN>.json` (numbered continuing past the
   highest existing index in that run, per `log-query-invocation.md`'s
   numbering rule — shared across every tool `rca-analyze` calls in a
   round, not a separate sequence per tool).
2. Append one line to `runs/run-NN/evidence/tools.jsonl` per
   `tool-ledger-format.md`, with `tool: "code-search"`, `table: null`
   (this capability does not touch the log tables), `keywords_in` set to
   `target` with its stated origin, and `result_ref` pointing at the file
   from step 1.
3. Carry forward into `analysis/round-N.json` only the specific fields a
   written claim rests on — the resolved module/symbol/location — never
   the raw payload.

## When source is unavailable

Two distinct cases, both routine and neither a HALT:

- **`is_lib: true`** — the module has no source in this checkout. Record
  the branch this hypothesis or finding depends on at `CODE_UNAVAILABLE`
  (per `evidence-tiers.md`) and continue the round at log level for that
  branch — a lib module caps how deep this one branch can be verified, it
  does not stop the round or eliminate the hypothesis.
- **`source_checkout` or `source_commit` is `null`** — this rung of the
  ladder cannot run for this issue at all. State this once, in the
  round's `open_notes`, rather than attempting the call and recording a
  failure per attempt.

## When the capability itself is unreachable

If the capability is not configured or fails to connect (distinct from
"the module is a lib" or "not found"): append an `error` ledger line
(`status: "error"`, the stated reason in `error`) and treat this rung as
unavailable for the rest of the round — do not retry it per hypothesis.
Never fabricate a resolved module or symbol to keep a round moving.
