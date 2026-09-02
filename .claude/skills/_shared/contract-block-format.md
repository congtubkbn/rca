# The `contract:` Block Format

Every skill in this suite (`rca-intake → rca-scope → rca-analyze ⟲ →
rca-conclude → rca-learn`) declares a `contract:` block
near the top of its `SKILL.md`, after the frontmatter. It is what lets a
skill be invoked directly and independently of the others — the skill
checks its own contract against the run bundle on disk instead of trusting
that some orchestrator already prepared its inputs. There is no
orchestrator in this suite; `/rca` is a thin dispatcher (see
`run-bundle-layout.md`), and direct invocation of any skill always works
and always wins.

## Shape

```yaml
contract:
  requires:        # must be present on disk, or supplied at invocation, to run at all
    - <run-bundle path or named input>
  optional:        # enriches the result if present; the skill runs without it
    - <run-bundle path or named input>
  produces:        # what this skill writes, and nowhere else
    - <run-bundle path>
  self_seedable: true|false   # can the engineer supply `requires` directly, bypassing upstream skills?
```

## Field semantics

- **`requires`** — the skill's precondition. If any entry is missing after
  checking both the run bundle and the invocation's own arguments, the
  skill HALTS and states which requirement is missing rather than
  guessing, defaulting, or fabricating a value. `requires` empty means the
  skill can always run (this is `rca-intake`'s position for everything
  except `issue_id`).
- **`optional`** — read if present, skipped if not. A skill must never
  *assume* an optional input is present; it degrades gracefully instead of
  erroring when it is absent.
- **`produces`** — the section(s) or file(s) this skill writes, and the
  full extent of what it writes. A skill writing outside its declared
  `produces` is a defect, regardless of whether it currently misbehaves —
  see `run-bundle-layout.md`'s "Per-Section Write Owners" table.
- **`self_seedable`** — whether the engineer can supply everything in
  `requires` directly at invocation time, without having run any upstream
  skill first. `rca-intake` is `self_seedable: true` by construction: it
  is the pipeline's entry point, so nothing upstream of it exists to skip.

`rca-intake`'s own contract block lives in its `SKILL.md`
(`.claude/skills/rca-intake/SKILL.md`) — that file is its single source of
truth; it is not repeated here, to avoid the two drifting apart. Later
skills declare their own contracts the same way, in their own `SKILL.md`;
this file does not need to change to accommodate them unless the shape of
`contract:` itself changes.
