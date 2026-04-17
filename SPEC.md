# DCF CLI — specification

A command-line tool for discounted cash flow analysis. All state is stored in a
`.dcf` directory that is **append-only**: nothing is ever overwritten or deleted.
Every assumption change, model run, and proposal session is recorded permanently
with a timestamp, producing a full audit trail by design.

---

## Table of contents

1. [Design principles](#1-design-principles)
2. [Directory structure](#2-directory-structure)
3. [Data formats](#3-data-formats)
4. [Commands](#4-commands)
   - [init](#41-init)
   - [assume](#42-assume)
   - [scenario](#43-scenario)
   - [run](#44-run)
   - [show](#45-show)
   - [sensitivity](#46-sensitivity)
   - [import](#47-import)
   - [proposal](#48-proposal)
   - [export](#49-export)
   - [log](#410-log)
   - [verify](#411-verify)
5. [Global flags](#5-global-flags)
6. [Exit codes](#6-exit-codes)

---

## 1. Design principles

**Append-only.** Every write operation either creates a new timestamped file or
appends one line to `log.jsonl`. Existing JSON artifacts are never modified.
Current state is derived by scanning records rather than by updating mutable
files. This makes the full history of the model recoverable at any point and
allows `verify` to detect tampering.

**Separation of assumptions and runs.** Assumptions are stored independently of
run outputs. A run is always a snapshot: it records the exact assumption set it
used alongside its output, so results are always reproducible.

**Versioned base inheritance.** Every change to the base assumption set
increments a base version number. Scenarios declare which base version they
inherit from. Running a scenario against a newer base requires an explicit
`dcf scenario rebase` — inheritance is never silent or automatic. This makes
the dependency between base and scenarios a visible, auditable relationship
rather than a hidden one.

**Proposal rationale is a first-class artifact.** When users or external
systems submit scenario proposals, their written rationale, cited sources, and
confidence can be stored alongside the numbers. The audit trail captures not
just what was assumed but why. The CLI stores and compares these artifacts; it
does not generate proposals itself.

**Human-readable storage.** All files are JSON or JSONL. The `.dcf` directory
should be readable without the CLI if necessary.

**Composable output.** Every command that produces data accepts `--format json`
so output can be piped to other tools.

---

## 2. Directory structure

```
.dcf/
├── config.json                        # project metadata, created once
├── log.jsonl                          # append-only event log, one JSON line per event
│
├── assumptions/                       # every assumption change ever recorded
│   ├── 0001_20240115_143022.json
│   ├── 0002_20240118_091533.json
│   └── ...
│
├── scenarios/                         # every scenario revision ever recorded
│   ├── 0001_20240115_143022_base.json
│   ├── 0002_20240118_091533_bull.json
│   ├── 0003_20240118_091700_bear.json
│   └── ...
│
├── runs/                              # every model run, full inputs and outputs
│   ├── r001_20240115_143500.json
│   ├── r002_20240118_094210.json
│   └── ...
│
├── imports/                           # raw imported financial data
│   ├── 0001_20240110_income_statement.csv
│   └── ...
│
├── historicals/                       # parsed historical statement records
│   ├── 0001_20240110_income_statement.json
│   └── ...
│
├── import_maps/                       # import column mapping revisions
│   ├── 0001_20240110.json
│   └── ...
│
└── proposals/                         # participant proposal sessions
    └── sessions/
        ├── s001_20240120_110000/
        │   ├── manifest.json          # session metadata
        │   ├── proposals/
        │   │   ├── p001_20240120_111000.json
        │   │   └── p002_20240120_112000.json
        │   └── consensus.json         # optional agreed assumption set
        └── ...
```

### Naming conventions

| Entity | Pattern | Example |
|---|---|---|
| Assumption record | `{seq}_{timestamp}.json` | `0004_20240120_093011.json` |
| Scenario revision | `{seq}_{timestamp}_{name}.json` | `0007_20240120_110000_bull.json` |
| Historical record | `{seq}_{timestamp}_{statement}.json` | `0003_20240110_income_statement.json` |
| Run | `r{seq}_{timestamp}.json` | `r007_20240122_141500.json` |
| Proposal session | `s{seq}_{timestamp}/` | `s002_20240123_090000/` |
| Sequence numbers | zero-padded to 4 digits | `0001`, `0042` |
| Timestamps | `YYYYMMDD_HHMMSS` UTC | `20240120_093011` |

---

## 3. Data formats

### 3.1 `config.json`

Created by `dcf init`. Never modified after creation.

```json
{
  "version": "1.0",
  "company": "Acme Corp",
  "created_at": "2024-01-15T14:30:22Z",
  "author": "jane",
  "currency": "USD",
  "fiscal_year_end": "12-31",
  "projection_years": 10
}
```

### 3.2 Assumption record

Each call to `dcf assume set` appends one new file.

```json
{
  "seq": 4,
  "base_version": 3,
  "timestamp": "2024-01-20T09:30:11Z",
  "author": "jane",
  "key": "revenue.growth_rate",
  "value": 0.12,
  "years": [1, 2, 3, 4, 5],
  "note": "revised upward after Q4 actuals",
  "supersedes": 2
}
```

`supersedes` references the sequence number of the previous record for this key,
providing an explicit linked history. `years` is omitted for scalar assumptions
that apply to all periods.

`base_version` is an integer that increments each time any base assumption
changes. It is the authoritative identifier for a particular state of the base
assumption set. `dcf assume set` always increments this counter and records the
new value on the assumption record. The current base version is the highest
`base_version` value across all assumption records.

### 3.3 Scenario revision

```json
{
  "seq": 7,
  "name": "bull",
  "created_at": "2024-01-18T09:15:33Z",
  "updated_at": "2024-01-20T11:00:00Z",
  "base_version": 3,
  "provenance": {
    "source": "scenario",
    "session_id": null,
    "proposal_id": null,
    "participant_id": null
  },
  "overrides": [
    {
      "key": "revenue.growth_rate",
      "value": 0.18,
      "years": [1, 2, 3, 4, 5]
    },
    {
      "key": "terminal.growth_rate",
      "value": 0.03
    }
  ],
  "rebase_history": [
    {
      "from_version": 1,
      "to_version": 3,
      "timestamp": "2024-01-20T11:00:00Z",
      "author": "jane",
      "note": "picked up updated WACC and tax rate"
    }
  ]
}
```

`base_version` records which version of the base assumption set this scenario
inherits from. This is set at creation time and updated only by an explicit
`dcf scenario rebase`. Scenario state is append-only: `create`, `set`, and
`rebase` each write a new scenario revision file. The current definition for a
scenario is the highest-`seq` revision with that `name`.

`provenance` records where the revision came from. Manual `scenario create` and
`scenario set` operations use `"source": "scenario"`. Revisions promoted from
participant proposals use `"source": "proposal"` and include the source
session, proposal, and participant ids.

`rebase_history` is a log of every rebase operation, recording what base
version the scenario moved from and to, when, and by whom. Each new revision
copies the prior `rebase_history` and appends the new entry when applicable.

### 3.4 Import map revision

```json
{
  "seq": 1,
  "timestamp": "2024-01-10T12:00:00Z",
  "author": "jane",
  "statement": "income-statement",
  "source_file": "0001_20240110_income_statement.csv",
  "columns": {
    "Revenue": "revenue",
    "EBIT": "ebit",
    "D&A": "depreciation_amortization"
  }
}
```

Import maps are append-only for the same reason assumptions are append-only.
When column mappings change, the CLI writes a new import map revision rather
than editing an existing mapping file. The current map for a statement is the
highest-`seq` revision for that statement.

### 3.5 Historical record

```json
{
  "seq": 3,
  "timestamp": "2024-01-10T12:05:00Z",
  "author": "jane",
  "statement": "income-statement",
  "fiscal_year": 2023,
  "source_file": "imports/0001_20240110_income_statement.csv",
  "import_map_seq": 1,
  "values": {
    "revenue": 1200000000,
    "gross_profit": 720000000,
    "ebit": 210000000,
    "depreciation_amortization": 45000000
  }
}
```

Historical records are the parsed, normalized form of imported source files.
Runs use the latest historical record for each statement and fiscal year unless
a future command explicitly pins a historical sequence.

### 3.6 Run record

```json
{
  "id": "r007",
  "timestamp": "2024-01-22T14:15:00Z",
  "author": "jane",
  "tag": "pre-board v1",
  "scenario": "base",
  "assumption_seq": 6,
  "scenario_seq": null,
  "base_version": 3,
  "inputs": {
    "revenue.growth_rate": [0.12, 0.12, 0.12, 0.08, 0.08],
    "margins.ebit": 0.22,
    "wacc": 0.09,
    "terminal.growth_rate": 0.025,
    "tax_rate": 0.21,
    "capex.pct_revenue": 0.04
  },
  "outputs": {
    "enterprise_value": 4820000000,
    "equity_value": 4210000000,
    "implied_share_price": 42.10,
    "terminal_value": 3740000000,
    "terminal_value_pct": 0.776,
    "projection_years": 10,
    "free_cash_flows": [
      {"year": 1, "fcf": 180000000, "pv": 165138000},
      {"year": 2, "fcf": 202000000, "pv": 170007000}
    ],
    "income_statement": {},
    "balance_sheet": {},
    "cash_flow_statement": {}
  }
}
```

The full resolved input set is stored with every run so results are always
independently reproducible without needing to reconstruct assumption history.

`scenario_seq` is `null` for the base case and records the exact scenario
revision used for named scenarios.

### 3.7 Proposal session manifest

```json
{
  "session_id": "s002",
  "timestamp": "2024-01-23T09:00:00Z",
  "model_run": "r007",
  "participants": [
    {"id": "jane", "type": "human", "display_name": "Jane"},
    {"id": "external-bear", "type": "external", "display_name": "External Bear Case"}
  ],
  "status": "complete",
  "consensus_proposal_id": "p004"
}
```

Proposal sessions group related scenario proposals from human users or external
systems. The CLI records submitted proposals and can compare, run, and promote
them. Any workflow that generates proposals, revisions, or consensus outside
direct CLI input is the responsibility of the calling application or external
orchestration layer.

### 3.8 Proposal record

Each file under `proposals/sessions/<session>/proposals/` is one proposed
scenario assumption set. Proposals are separate JSON artifacts rather than
lines in a shared JSONL file so each submitted proposal can be hash-verified
without mutating a previously logged artifact.

```json
{
  "proposal_id": "p003",
  "timestamp": "2024-01-23T09:10:00Z",
  "participant_id": "jane",
  "participant_type": "human",
  "label": "Jane downside case",
  "base_version": 3,
  "scenario_seq": null,
  "overrides": [
    {
      "key": "revenue.growth_rate",
      "value": 0.05,
      "years": [1, 2, 3, 4, 5],
      "rationale": "Lower renewal assumptions after customer cohort review"
    },
    {
      "key": "wacc",
      "value": 0.105,
      "rationale": "Higher rate environment and small-cap liquidity premium"
    }
  ],
  "source": {
    "kind": "manual",
    "command": "dcf proposal submit --participant jane --label \"Jane downside case\""
  }
}
```

`scenario_seq` is populated when the proposal was created from an existing
scenario revision. A proposal can be run directly, compared against other
proposals, or promoted into a named scenario revision.

### 3.9 `log.jsonl`

One JSON object per line, appended for every significant event. Events that
create a file include an `artifact` object with the relative path and SHA-256
hash of the file after it is written. Log entries also include a hash chain:
`prev_entry_hash` is the hash of the previous canonical JSONL entry, or `null`
for the first entry.

```jsonl
{"ts":"2024-01-15T14:30:22Z","event":"init","author":"jane","company":"Acme Corp","artifact":{"path":"config.json","sha256":"..."},"prev_entry_hash":null}
{"ts":"2024-01-15T14:35:01Z","event":"assume_set","author":"jane","key":"wacc","value":0.09,"seq":1,"artifact":{"path":"assumptions/0001_20240115_143501.json","sha256":"..."},"prev_entry_hash":"..."}
{"ts":"2024-01-15T14:40:00Z","event":"run","author":"jane","run_id":"r001","scenario":"base","tag":null,"artifact":{"path":"runs/r001_20240115_144000.json","sha256":"..."},"prev_entry_hash":"..."}
{"ts":"2024-01-20T09:00:00Z","event":"proposal_session","author":"jane","session_id":"s001","participants":["jane","alex"],"artifact":{"path":"proposals/sessions/s001_20240120_090000/manifest.json","sha256":"..."},"prev_entry_hash":"..."}
```

The log hash chain detects modified or reordered log entries. Like any
self-contained local append-only log, it cannot prove that the final log entries
were not truncated unless the latest entry hash has been anchored externally.

---

## 4. Commands

### 4.1 `init`

Initialise a new DCF project in the current directory.

```
dcf init [options]
```

| Option | Description |
|---|---|
| `--company <name>` | Company name stored in config |
| `--author <name>` | Author name (defaults to `$USER`) |
| `--currency <code>` | Currency code, default `USD` |
| `--fiscal-year-end <MM-DD>` | Fiscal year end, default `12-31` |
| `--years <n>` | Projection period in years, default `10` |

**Behaviour:**
- Creates `.dcf/` directory and all subdirectories
- Writes `config.json` and initialises `log.jsonl`
- Fails with an error if `.dcf/` already exists
- Creates an initial `base` scenario revision with no overrides

**Example:**
```bash
dcf init --company "Acme Corp" --author jane
```

---

### 4.2 `assume`

Manage model assumptions. All subcommands append a new record; nothing is
overwritten.

#### `assume set`

```
dcf assume set <key> <value> [options]
```

| Option | Description |
|---|---|
| `--years <range>` | Year range, e.g. `1-5` or `1,3,5` |
| `--note <text>` | Optional note explaining the change |
| `--author <name>` | Override default author |

**Key naming convention:** dot-separated hierarchy.

| Key | Description |
|---|---|
| `revenue.growth_rate` | Revenue growth rate |
| `margins.gross` | Gross margin |
| `margins.ebit` | EBIT margin |
| `capex.pct_revenue` | Capex as % of revenue |
| `working_capital.days_receivable` | Debtor days |
| `working_capital.days_inventory` | Inventory days |
| `working_capital.days_payable` | Creditor days |
| `wacc` | Weighted average cost of capital |
| `terminal.growth_rate` | Terminal growth rate |
| `terminal.exit_multiple` | Terminal exit multiple (alternative to TGR) |
| `tax_rate` | Effective tax rate |
| `net_debt` | Net debt for equity bridge |
| `shares_outstanding` | Shares outstanding |

**Examples:**
```bash
dcf assume set revenue.growth_rate 0.12 --years 1-5
dcf assume set revenue.growth_rate 0.08 --years 6-10
dcf assume set wacc 0.09 --note "based on re-levered beta 1.2"
dcf assume set terminal.growth_rate 0.025
```

#### `assume list`

Show the current resolved assumption set — the latest value for every key.

```
dcf assume list [--format json]
```

#### `assume get`

Show the current value of a single assumption.

```
dcf assume get <key>
```

#### `assume history`

Show every value a key has ever taken, in chronological order.

```
dcf assume history <key>
```

#### `assume diff`

Show what changed between two assumption sequence numbers.

```
dcf assume diff <seq_a> <seq_b>
```

---

### 4.3 `scenario`

Manage named scenarios. Each scenario stores overrides relative to the base
assumption set and declares the base version it was built against. Inheritance
is never automatic — updating a scenario to a newer base always requires an
explicit `dcf scenario rebase`.

#### `scenario create`

```
dcf scenario create <name> [options]
```

| Option | Description |
|---|---|
| `--from <scenario>` | Copy overrides from an existing scenario |

**Behaviour:**
- Records the current base version in the scenario revision
- A scenario created with `--from` copies the source scenario's overrides and
  inherits the current base version at time of creation

**Example:**
```bash
dcf scenario create bull --from base
dcf scenario create bear --from base
```

#### `scenario set`

Set an assumption override within a named scenario.

```
dcf scenario set <name> <key> <value> [--years <range>]
```

**Behaviour:** writes a new scenario revision with the updated overrides. Does
not change the scenario's `base_version` -- use `rebase` for that.

**Example:**
```bash
dcf scenario set bull revenue.growth_rate 0.18 --years 1-5
dcf scenario set bear revenue.growth_rate 0.04 --years 1-5
dcf scenario set bear wacc 0.11
```

#### `scenario rebase`

Explicitly update a scenario to inherit from a newer base version.

```
dcf scenario rebase <name> [options]
```

| Option | Description |
|---|---|
| `--to <version>` | Rebase to a specific base version rather than latest |
| `--note <text>` | Note explaining why the rebase was done |
| `--dry-run` | Show what would change without writing anything |
| `--force` | Proceed despite override conflicts |

**Behaviour:**
- Resolves the scenario's overrides against the new base version
- Checks for conflicts — cases where a base assumption that the scenario
  overrides has also changed in the new base — and reports them
- On conflict, stops and requires `--force` to proceed, with an explicit
  acknowledgement that the override may be stale
- Writes a new scenario revision with the updated `base_version` and a new entry
  in `rebase_history`
- Appends an event to `log.jsonl`

**Conflict output example:**
```
  Conflict: bear.wacc overrides base.wacc
    scenario sets : 0.11
    base was       : 0.09  (version 2)
    base is now    : 0.10  (version 4)
  This override may be stale. Update it first with:
    dcf scenario set bear wacc <new_value>
  Or accept as-is with --force.
```

**Example:**
```bash
dcf scenario rebase bear
dcf scenario rebase bear --note "picked up updated macro assumptions"
dcf scenario rebase bear --dry-run
```

#### `scenario list`

```
dcf scenario list
```

Output includes each scenario's name, its pinned base version, the current base
version, and rebase status.

```
  NAME    BASE_VERSION  CURRENT  STATUS
  base    —             —        —
  bull    3             3        up to date
  bear    2             3        rebase available
```

#### `scenario show`

Show the full resolved assumption set for a scenario, clearly distinguishing
base values from overrides. Warns if the scenario's base version is behind
current.

```
dcf scenario show <name>
```

#### `scenario compare`

Show assumptions for multiple scenarios side by side, highlighting differences.

```
dcf scenario compare <name> [<name> ...]
```

**Example:**
```bash
dcf scenario compare base bull bear
```

---

### 4.4 `run`

Execute the DCF model and store the full result.

```
dcf run [options]
```

| Option | Description |
|---|---|
| `--scenario <name>` | Run against a named scenario, default `base` |
| `--scenarios <names>` | Run multiple scenarios, space-separated |
| `--tag <text>` | Human-readable label for this run |
| `--author <name>` | Override default author |

**Behaviour:**
- Resolves the full assumption set for the scenario
- Executes the three-statement model and DCF calculation
- Writes a complete run record including all inputs and outputs
- Appends an entry to `log.jsonl`
- Prints a brief summary to stdout on completion

**Examples:**
```bash
dcf run
dcf run --scenario bull --tag "management case"
dcf run --scenarios base bull bear --tag "board pack scenarios"
```

---

### 4.5 `show`

Inspect run results.

#### `show` (summary)

Show a summary of the latest run or a specified run.

```
dcf show [options]
```

| Option | Description |
|---|---|
| `--run <id>` | Show a specific run by id, e.g. `r007` |
| `--tag <text>` | Show the most recent run with this tag |
| `--scenario <name>` | Show the most recent run for this scenario |
| `--format json` | Machine-readable output |

**Output includes:** enterprise value, equity value, implied share price,
terminal value and its percentage of total value, WACC, terminal growth rate.

#### `show income-statement`

```
dcf show income-statement [--run <id>] [--format json]
```

#### `show balance-sheet`

```
dcf show balance-sheet [--run <id>] [--format json]
```

#### `show cash-flows`

```
dcf show cash-flows [--run <id>] [--format json]
```

#### `show waterfall`

Enterprise value bridge showing the contribution of each projected year's free
cash flow and the terminal value to total enterprise value.

```
dcf show waterfall [--run <id>]
```

#### `show history`

List every run ever executed with id, timestamp, tag, scenario, and headline
valuation.

```
dcf show history [options]
```

| Option | Description |
|---|---|
| `--since <date>` | Filter to runs after this date |
| `--scenario <name>` | Filter to a specific scenario |
| `--limit <n>` | Show only the n most recent runs |

---

### 4.6 `sensitivity`

Run sensitivity analysis across two assumptions and display a table of
enterprise values.

```
dcf sensitivity <key_a> [<range_a>] <key_b> [<range_b>] [options]
```

Ranges are specified as `min:max:steps`, e.g. `0.07:0.12:5` produces five
evenly-spaced values from 7% to 12%.

If ranges are omitted, defaults are used:

| Key | Default range |
|---|---|
| `wacc` | ±2pp around current value in 5 steps |
| `terminal.growth_rate` | 1% to 4% in 5 steps |
| `revenue.growth_rate` | ±3pp around current value in 5 steps |

| Option | Description |
|---|---|
| `--run <id>` | Base from a specific run, default latest |
| `--scenario <name>` | Base from a specific scenario |
| `--metric <name>` | Output metric, default `enterprise_value` |
| `--format json` | Machine-readable output |

**Metrics:** `enterprise_value`, `equity_value`, `implied_share_price`

**Example:**
```bash
dcf sensitivity wacc 0.07:0.12:5 terminal.growth_rate 0.01:0.04:5
dcf sensitivity wacc terminal.growth_rate --scenario bear
```

---

### 4.7 `import`

Import historical financial statements. Raw files are stored in `.dcf/imports/`
and parsed data is written as normalized records in `.dcf/historicals/`.

```
dcf import <statement> <file> [options]
```

| Statement | Description |
|---|---|
| `income-statement` | Historical P&L |
| `balance-sheet` | Historical balance sheet |
| `cash-flows` | Historical cash flow statement |

| Option | Description |
|---|---|
| `--year <yyyy>` | Fiscal year of the data |
| `--format <fmt>` | File format: `csv` (default) or `json` |

**Example:**
```bash
dcf import income-statement financials_2023.csv --year 2023
dcf import balance-sheet financials_2023.csv --year 2023
```

CSV files should have a header row. Column names are mapped to internal keys
via import map revisions that `dcf import` generates on first use and stores in
`.dcf/import_maps/` for subsequent imports.

If the CLI cannot map a column confidently, it fails before writing parsed model
state and prints the unmapped column names. The user must provide mappings and
rerun the import, producing a new import map revision and a new raw import
artifact.

Successful imports write two artifacts: the raw source copy under
`.dcf/imports/` and the parsed historical record under `.dcf/historicals/`.
Both artifacts are recorded in `log.jsonl`.

---

### 4.8 `proposal`

Store and compare proposed scenario assumption sets. This command group is for
data capture and DCF calculation only: it does not generate proposals, call LLM
APIs, decide winners, or orchestrate review workflows. External tools may use
these commands and file formats to persist their outputs.

#### `proposal session`

Create a proposal session that groups related scenario proposals.

```
dcf proposal session create [options]
```

| Option | Description |
|---|---|
| `--participant <name>` | Participant id; may be repeated |
| `--label <text>` | Human-readable session label |
| `--run <id>` | Optional model run used as the baseline |

#### `proposal submit`

Submit a proposed scenario assumption set from a user or external system.

```
dcf proposal submit --session <id> [options]
```

| Option | Description |
|---|---|
| `--participant <name>` | Participant submitting the proposal |
| `--participant-type <type>` | `human`, `external`, or `system`; default `human` |
| `--label <text>` | Human-readable proposal label |
| `--from-scenario <name>` | Seed the proposal from an existing scenario |
| `--set <key=value>` | Add or replace one proposed value; may be repeated |
| `--rationale <key=text>` | Rationale for one proposed value; may be repeated |
| `--source <text>` | Source note or URI for the proposal; may be repeated |
| `--format json` | Machine-readable output |

**Examples:**
```bash
dcf proposal session create --participant jane --participant alex --label "IC cases"
dcf proposal submit --session s002 --participant jane --label "Jane downside case" \
  --set revenue.growth_rate=0.05 --set wacc=0.105 \
  --rationale wacc="Higher rate environment and small-cap liquidity premium"
dcf proposal submit --session s002 --participant external-bear \
  --participant-type external --from-scenario bear --set terminal.growth_rate=0.015
```

#### `proposal show`

Inspect a proposal session or a single proposal.

```
dcf proposal show [options]
```

| Option | Description |
|---|---|
| `--session <id>` | Session to inspect, default latest |
| `--participant <name>` | Show one participant's proposals and rationale |
| `--proposal <id>` | Show one proposal |
| `--consensus` | Show the optional consensus proposal |
| `--format json` | Machine-readable output |

#### `proposal compare`

Compare proposals side by side and optionally run each proposal through the DCF
model.

```
dcf proposal compare --session <id> [options]
```

| Option | Description |
|---|---|
| `--proposals <ids>` | Proposal ids to compare, default all proposals in the session |
| `--metric <name>` | Output metric, default `implied_share_price` |
| `--run` | Execute the DCF model for each proposal before comparing |
| `--format json` | Machine-readable output |

**Example:**
```bash
dcf proposal compare --session s002 --run
dcf proposal compare --session s002 --proposals p001 p003 p004 --metric enterprise_value
```

#### `proposal run`

Run the DCF model using a specific proposal or the optional consensus proposal.

```
dcf proposal run --session <id> [--proposal <id>] [--tag <text>]
```

#### `proposal consensus`

Mark one proposal as the consensus proposal for a session. This records the
selection only; the CLI does not decide consensus.

```
dcf proposal consensus --session <id> --proposal <id>
```

#### `proposal promote`

Promote a proposal into a named scenario revision.

```
dcf proposal promote --session <id> --proposal <id> --scenario <name>
```

**Behaviour:**
- Writes a new scenario revision using the proposal's overrides
- Preserves the proposal id, participant id, and session id on the scenario
  revision provenance
- Appends an event to `log.jsonl`

#### `proposal sensitivity`

Run sensitivity analysis across all proposal sets in a session simultaneously,
producing a multi-scenario comparison.

```
dcf proposal sensitivity --session <id>
```

---

### 4.9 `export`

Export run results to external formats. Exports are written to the current
working directory, not to `.dcf/`.

```
dcf export <format> [options]
```

| Format | Description |
|---|---|
| `excel` | Multi-sheet xlsx workbook |
| `pdf` | Formatted PDF report |
| `csv` | CSV files, one per statement |

| Option | Description |
|---|---|
| `--run <id>` | Run to export, default latest |
| `--scenarios <names>` | Export multiple scenarios into one workbook |
| `--tag <text>` | Label for the export |
| `--out <path>` | Output path, default current directory |

**Examples:**
```bash
dcf export excel --run r007 --tag "board pack"
dcf export pdf --run r007
dcf export csv --scenarios base bull bear --out ./output/
```

---

### 4.10 `log`

Inspect the append-only event log.

```
dcf log [options]
```

| Option | Description |
|---|---|
| `--runs` | Show only run events |
| `--assumptions` | Show only assumption change events |
| `--proposals` | Show only proposal session and proposal events |
| `--since <date>` | Filter to events after this date |
| `--author <name>` | Filter by author |
| `--format json` | Raw JSONL output |
| `--limit <n>` | Show only the n most recent events |

**Example:**
```bash
dcf log --runs --since 2024-01-01
dcf log --assumptions --author jane
dcf log --proposals
```

---

### 4.11 `verify`

Verify the integrity of the `.dcf` directory. Checks that no file has been
modified after creation by comparing current file hashes against hashes
recorded in the log at write time.

```
dcf verify [options]
```

| Option | Description |
|---|---|
| `--fix` | Not available — the append-only guarantee means nothing can be fixed, only flagged |
| `--format json` | Machine-readable output |

**Behaviour:**
- Reads every file in `.dcf/`
- Computes SHA-256 hash of each file
- Compares artifact files against the hashes recorded in `log.jsonl` when each
  file was written
- Verifies the `log.jsonl` entry hash chain to detect modified or reordered log
  entries
- Reports any file whose hash does not match as tampered
- Reports any logged artifact path that is missing
- Reports any unlogged file under `.dcf/` except temporary lock files as
  unexpected
- Exits with code 0 if all files are clean, code 2 if any tampering is detected

**Note:** `verify` requires that every write operation records the file hash in
`log.jsonl` at the time of writing. This is handled automatically by the CLI.
Because `log.jsonl` is stored locally, `verify` cannot prove that trailing log
entries were not deleted unless the latest log entry hash has been anchored
outside the `.dcf` directory.

---

## 5. Global flags

These flags are accepted by all commands.

| Flag | Description |
|---|---|
| `--dir <path>` | Path to `.dcf` directory, default auto-discovered by walking up from cwd |
| `--author <name>` | Override author for this operation, default `$USER` |
| `--format json` | Output as JSON where supported |
| `--quiet` | Suppress informational output, print only results |
| `--no-color` | Disable coloured terminal output |
| `--help` | Show help for the command |

---

## 6. Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | General error (bad arguments, missing file, etc.) |
| `2` | Integrity error (`verify` detected tampered files) |
| `3` | Model error (assumptions incomplete, calculation failed) |
| `4` | External integration error (invalid imported proposal payload, unsupported source format, etc.) |
