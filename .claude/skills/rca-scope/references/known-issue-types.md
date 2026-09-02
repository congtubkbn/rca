# Known Issue Types — `rca-scope`'s Built-In Classification Reference

This is a small, hand-written lookup `rca-scope` consults when classifying
an issue from its PLM title/description. It is a convenience cache, not a
precondition (issue #5: "Classification does not require a hand-written
playbook to exist... Playbooks are a cache that accumulates, not a
precondition"). When nothing here matches, `rca-scope` proceeds generically
— it never forces an issue into the nearest-looking row of this table.

This is a **different thing** from `.rca/knowledge/playbooks/` (promoted,
reviewed playbooks written by `rca-learn`, issue #11). This file lives in
the repository and is hand-maintained; `knowledge/playbooks/` lives
per-workspace and accumulates from accepted runs, one explicit `promote`
action at a time. `rca-scope` reads only this file — it never reads
`knowledge/playbooks/`, which is `rca-analyze`'s resolution-ladder rung 6
concern instead (`resolution-ladder.md`).

## Matching rule

A row matches when the PLM title or description (case-insensitive) contains
any one of its `trigger_keywords`. The first matching row wins; if none
match, classification is `generic` (see `SKILL.md` step 3).

| `issue_type` | `trigger_keywords` | `tables_in_scope` | `layers` | `failure_indicator_keywords` (for time-anchor queries) |
|---|---|---|---|---|
| `volte_call_drop` | "volte", "voice call drop", "call dropped", "call disconnected" | `UE_3gpp_signaling_log`, `UE_Trace_log` | `PHY`, `RRC`, `NAS`, `IMS/SIP` | "BYE", "RRCConnectionRelease", "CallEnd" |
| `sms_failure` | "sms fail", "sms not received", "sms send fail", "text message fail" | `UE_3gpp_signaling_log` | `NAS`, `RRC` | "SMS delivery failure", "RP-ERROR", "CP-ERROR" |
| `no_service` | "no service", "no signal", "lost coverage", "searching for service" | `UE_3gpp_signaling_log`, `UE_Trace_log` | `RRC`, `NAS`, `PHY` | "cell selection failure", "out of service", "RRC_IDLE" |
| `emergency_call` | "emergency call", "sos call", "e911", "ecall" | `UE_3gpp_signaling_log`, `UE_Trace_log` | `RRC`, `NAS`, `IMS/SIP` | "EMERGENCY", "BYE", "CallEnd" |

## Generic fallback keyword set

Used for the time-anchor log query only when classification is `generic`
(no row matched), so a vague report is still analysable (issue #5, "a vague
report must still be analysable"). Not tied to any `issue_type`:

`"release"`, `"reject"`, `"failure"`, `"drop"`, `"timeout"`, `"abort"`,
`"disconnect"`

A keyword drawn from this list has its origin recorded in the ledger as
`"generic-fallback-keywords"`, never presented as if it were specific to
the issue's actual failure mode.
