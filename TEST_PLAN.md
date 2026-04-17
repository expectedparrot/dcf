# DCF CLI test plan

This plan describes the tests the implementation should satisfy. The runnable
tests in `tests/` include both spec contract tests and end-to-end CLI workflow
tests. As the implementation grows, each case below should either have direct
coverage or be split into smaller unit tests.

## 1. Project initialization

- `dcf init` creates `.dcf/`, all required subdirectories, `config.json`, an
  initial base scenario revision, and `log.jsonl`.
- `dcf init` persists `company`, `author`, `currency`, `fiscal_year_end`, and
  `projection_years`.
- `dcf init` fails when `.dcf/` already exists.
- Every artifact created by `init` has a matching log entry with path and
  SHA-256 hash.

## 2. Append-only storage

- `assume set` creates a new file under `.dcf/assumptions/` and never edits an
  existing assumption file.
- `scenario create`, `scenario set`, and `scenario rebase` create new scenario
  revision files and never edit prior scenario revisions.
- `proposal submit`, `proposal consensus`, and `proposal promote` append or
  create new artifacts without mutating prior proposal or scenario artifacts.
- Sequence numbers remain monotonic and zero-padded.
- Timestamps are UTC and match `YYYYMMDD_HHMMSS` in filenames.

## 3. Assumptions

- `assume set` increments `base_version` for base assumptions.
- `supersedes` points to the prior assumption record for the same key and year
  scope.
- `assume list` resolves the latest value for every key.
- `assume get` returns the current value for a single key.
- `assume history` returns values in chronological order.
- `assume diff` reports changes between two assumption sequence numbers.
- Year-specific assumptions resolve correctly when multiple year ranges exist.

## 4. Scenarios

- `scenario create` pins the current base version.
- `scenario set` writes a new scenario revision without changing
  `base_version`.
- `scenario rebase` updates `base_version` only through an explicit rebase.
- Rebase conflict detection fires when both the base and scenario override the
  same key.
- `scenario list` reports up-to-date and rebase-available statuses correctly.
- `scenario show` distinguishes inherited base values from overrides.
- `scenario compare` highlights differences across named scenarios.
- Scenario revisions promoted from proposals retain provenance.

## 5. Imports and historicals

- `import` stores the raw source file under `.dcf/imports/`.
- `import` writes parsed normalized records under `.dcf/historicals/`.
- Import maps are versioned under `.dcf/import_maps/`.
- Unmapped columns fail before writing parsed historical state.
- Successful imports log both raw and parsed artifacts.
- Runs use the latest historical record for each statement and fiscal year.

## 6. DCF model runs

- `run` resolves the full input set for the selected scenario.
- `run` stores the full resolved inputs and full outputs.
- Base runs have `scenario_seq: null`.
- Scenario runs record the exact `scenario_seq` used.
- Multi-scenario runs create separate run records.
- Missing required assumptions exit with model error code `3`.
- Terminal growth and exit multiple terminal value methods are mutually
  exclusive or explicitly resolved.
- Equity value, implied share price, terminal value, and free cash flow present
  value calculations are deterministic and reproducible from the run record.

## 7. Proposal sessions

- `proposal session create` creates a proposal session manifest.
- `proposal submit` records participant id, participant type, label, base
  version, overrides, rationale, and sources.
- `proposal submit --from-scenario` seeds values from an existing scenario
  revision.
- `proposal show` displays session, participant, proposal, and consensus views.
- `proposal compare --run` executes the DCF model for each selected proposal and
  reports the requested metric.
- `proposal run` runs a selected proposal or the recorded consensus proposal.
- `proposal consensus` records a selected proposal id without deciding
  consensus itself.
- `proposal promote` writes a scenario revision with source provenance back to
  session, proposal, and participant.
- The package never generates proposals, calls LLM APIs, simulates agents, or
  orchestrates review workflows.

## 8. Sensitivity analysis

- Default ranges are applied when ranges are omitted.
- Explicit `min:max:steps` ranges include both endpoints.
- Supported metrics are `enterprise_value`, `equity_value`, and
  `implied_share_price`.
- Sensitivity output is stable in both table and JSON formats.
- Proposal sensitivity runs across proposal sets without mutating proposals.

## 9. Display and export

- `show` defaults to the latest run.
- `show --run`, `show --tag`, and `show --scenario` select the correct run.
- Statement views return income statement, balance sheet, and cash flow outputs.
- `show waterfall` reconciles to enterprise value.
- `export` writes to the requested external path, not `.dcf/`.
- Exporting multiple scenarios includes one result set per scenario.

## 10. Integrity verification

- `verify` succeeds for a clean `.dcf` directory.
- `verify` detects modified artifact contents.
- `verify` detects missing logged artifacts.
- `verify` detects unlogged files except allowed temporary lock files.
- `verify` detects modified or reordered log entries through the hash chain.
- `verify` reports the limitation that local logs cannot prove trailing
  truncation without an external anchor.
- Tampering exits with integrity error code `2`.

## 11. JSON output and errors

- Every data-producing command supporting `--format json` emits valid JSON.
- Human-readable output is stable enough for snapshot tests where appropriate.
- Bad arguments exit with code `1`.
- Model calculation failures exit with code `3`.
- Invalid imported external proposal payloads exit with code `4`.
