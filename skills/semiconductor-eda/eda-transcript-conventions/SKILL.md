---
name: eda-transcript-conventions
description: Report RTL findings in the severity-tagged message format used by commercial EDA tools (Cadence Xcelium/Genus/Innovus, Synopsys VCS/Design Compiler/SpyGlass). Use when writing lint/synthesis/simulation findings, sign-off summaries, or any output rendered into an EDA-style transcript console.
---

# EDA Transcript Conventions

Engineers reading your output are used to commercial tool transcripts. Match that
format so findings are scannable, greppable, and severity-sortable.

## Message format

Emit one finding per line, most severe first:

```
<SEV>-[<TAG>] <object>: <what is wrong>
    <file>:<line>
    Suggestion: <the minimal corrective action>
```

`<SEV>` is one of — and the words mean exactly this:

| Severity | Meaning | Gates sign-off? |
|---|---|---|
| `FATAL` | Tool could not complete; no result exists | yes |
| `ERROR` | Design is wrong or unsynthesizable | yes |
| `WARN`  | Legal but risky; silicon-visible under some condition | no, but must be waived explicitly |
| `NOTE`  | Style/consistency; no functional consequence | no |
| `INFO`  | Progress, statistics, environment | no |

`<TAG>` is a short stable uppercase token so findings can be grepped and waived
by class: `LINT`, `SYNTH`, `LATCH`, `CDC`, `RST`, `WIDTH`, `FSM`, `ARITH`, `UNCONN`,
`MULTIDRV`, `SCOREBOARD`, `FORMAL`, `LEC`, `COV`, `TIMING`, `AREA`, `POWER`.

Examples:

```
ERROR-[LATCH] gamma.lut_rd: inferred latch — `always @*` has an incomplete branch
    rtl/gamma.v:118
    Suggestion: assign a default before the if/case, or complete the else branch.

WARN-[RST] gamma.count: reset polarity inconsistent with module convention
    rtl/gamma.v:64
    Suggestion: the module resets active-low (rst_n); use `if (!rst_n)`.

NOTE-[WIDTH] gamma.sum: 9-bit expression truncated to 8-bit target
    rtl/gamma.v:141
    Suggestion: state the intent with an explicit cast or a widened target.

INFO-[SYNTH] gamma: 41 cells, 26 flops, 0 latches
```

## Run banners

Open and close each flow stage the way a tool does, so elapsed time and verdict are
always visible:

```
=============================================================
  Stage : synthesize            Tool : yosys
  Design: gamma                 Started: 14:02:11
=============================================================
...
INFO-[SYNTH] gamma: 41 cells, 26 flops, 0 latches
-------------------------------------------------------------
  Stage synthesize : PASS        Elapsed: 00:00:03
  Errors: 0   Warnings: 1   Notes: 2
=============================================================
```

## Sign-off summary table

End a multi-stage run with a verdict table, never a prose paragraph:

```
STAGE         STATUS   GATING   DETAIL
lint          PASS     yes      verilator: 0 issues
design        PASS     yes      8/8 rule checks
synthesize    PASS     yes      yosys: 0 latches, 26 flops
simulate      PASS     yes      13/13 patterns bit-exact (2,048 px)
-------------------------------------------------------------
VERDICT: SIGNED_OFF   Score: 96/100   Grade: A
```

## Rules

- **`skip` is not `pass`.** A skipped stage means evidence is missing. Report it as
  `skip` and say what would have to run to turn it into a pass.
- **Never inflate severity to seem thorough, never deflate it to seem clean.** A
  latch inference is an `ERROR`; a naming inconsistency is a `NOTE`. Do not mix them.
- **One finding, one line, one location.** If you cannot name a file and line, say
  `(location unknown)` rather than omitting the field.
- **No marketing language.** Not "blazingly fast", not "100% secure", not
  "production-ready". Report measurements and what they do and do not cover.
- **Every WARN needs a disposition** — fix it, or waive it with a stated reason.
  An unwaived warning carried into sign-off is itself a finding.
- When you have no findings, say so explicitly: `INFO-[LINT] gamma: 0 issues` —
  an empty response reads as a crashed tool.
