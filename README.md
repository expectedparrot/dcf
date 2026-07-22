# dcf — append-only discounted cash flow valuation CLI
<!-- id: dcf/dcf -->

dcf builds auditable discounted-cash-flow valuations from assumptions, scenarios, proposal sessions, runs, sensitivity sweeps, and exports. The agent collaborates with the user to pin down cash-flow assumptions, discounting logic, terminal value method, and scenario structure, then returns JSON/Excel-ready valuation outputs with an append-only history.

## When to use this
<!-- id: dcf/when-to-use -->

- The decision reduces to a dollar-denominated enterprise value, equity value, NPV, or investment return.
- Cash flows over a finite forecast horizon can be projected with defensible assumptions.
- A discount rate, terminal method, and scenario set can be stated explicitly.
- The user needs an auditable record of assumptions, proposal changes, runs, and exports.

## When this is a stretch (and how to adapt)
<!-- id: dcf/when-stretch -->

- The user has only rough directional economics. Still use dcf by creating a base case with wide bull/bear scenarios and sensitivity sweeps.
- The outcome includes non-financial criteria. Run dcf for the monetary leg, then feed the result as one criterion into [mcda](#mcda/mcda).
- The user is comparing mutually exclusive strategic paths. Create one scenario per path if the same model structure holds; otherwise create separate projects and compare exported summaries.
- The user wants option value under uncertainty. Use dcf for base economics and pair with [raiffa](#raiffa/raiffa) when staged decisions or value of information dominate.

## Decision rule for the calling agent
<!-- id: dcf/decision-rule -->

Before dispatching to dcf, confirm:

1. The target output is a single monetary value or a scenario table of monetary values.
2. Forecast drivers can be converted into period cash flows.
3. The user can defend a discount rate or wants help selecting a sensitivity range.
4. Terminal value or explicit exit assumptions are relevant.

If yes to the first two and at least one of the last two, dcf is the right method.

## Inputs and elicitation
<!-- id: dcf/inputs -->

### Valuation objective
<!-- id: dcf/inputs-objective -->

What it is: the asset, project, company, or investment being valued and the decision the valuation informs.

How the agent elicits this:
- Ask whether the output should be enterprise value, equity value, project NPV, or investment committee comparison.
- Ask the valuation date, currency, forecast horizon, and whether debt/cash adjustments matter.
- Ask whether the user needs one base case, multiple scenarios, or proposal review.

Default to suggest: a 5-year forecast plus terminal value for a going concern; explicit finite cash flows for a project.

Fallback: if details are thin, create a base case with placeholder assumptions and mark uncertain drivers for sensitivity.

### Cash-flow assumptions
<!-- id: dcf/inputs-cash-flows -->

What it is: revenue, margin, costs, capex, working capital, taxes, and any non-operating adjustments needed to produce free cash flow.

How the agent elicits this:
- Ask for historical revenue and the drivers of growth.
- Ask which margin/cost lines are stable versus uncertain.
- Ask whether capex, depreciation, taxes, and working capital can be modeled as percentages or explicit amounts.

Default to suggest: revenue growth, EBITDA margin, tax rate, capex as percent of revenue, working capital change, and terminal growth.

Fallback: use simplified free-cash-flow inputs directly when operating detail is unavailable.

### Discounting and terminal method
<!-- id: dcf/inputs-discounting -->

What it is: WACC or required return, terminal growth or exit multiple, and timing convention.

How the agent elicits this:
- Ask whether the user has a WACC, hurdle rate, or comparable-company multiple.
- Suggest a sensitivity range around the discount rate and terminal growth/multiple.
- Clarify whether terminal value should be perpetuity growth, exit multiple, or no terminal value.

Default to suggest: perpetuity growth for mature going concerns; exit multiple for sponsor/acquisition cases.

Fallback: run both terminal methods as scenarios and compare dependence on terminal value.

## Outputs
<!-- id: dcf/outputs -->

All durable state lives under the selected DCF directory, usually `.dcf/`:

- Assumption records and scenario overrides — append-only inputs with author/time metadata.
- Run results — projected cash flows, discounted values, terminal value, NPV/EV/equity outputs.
- Sensitivity outputs — parameter sweeps over discount rates, terminal growth, margins, or other drivers.
- Proposal session artifacts — submitted assumption changes, comparison runs, and promoted proposals.
- Excel exports — reviewable workbooks for stakeholders.

## Workflow
<!-- id: dcf/workflow -->

Canonical sequence:

1. `dcf init` — create the project store.
2. `dcf assume set <key> <value>` — enter base assumptions.
3. `dcf scenario create <name>` — create downside/base/upside or named alternatives.
4. `dcf scenario set <name> <key> <value>` — override assumptions by scenario.
5. `dcf verify` — check model completeness and structural validity.
6. `dcf run --scenario <name>` — compute valuation results.
7. `dcf sensitivity --scenario <name> ...` — test key drivers.
8. `dcf export ...` — emit Excel or downstream artifacts.

Use proposal commands when the user wants reviewed changes before promotion into the base model.

## Worked examples
<!-- id: dcf/examples -->

### Eliciting a project valuation
<!-- id: dcf/example-project-valuation -->

User: "Can you value a new product line?"

Agent: "Yes. Should the output be project NPV rather than enterprise value? I need forecast horizon, yearly free cash flow or drivers, discount rate, and whether there is terminal value. A common starting point is five years, no terminal value for a finite project, and a hurdle-rate sensitivity."

User: "Use five years, 12% hurdle, cash flows from $1M to $3M."

Agent: "I'll set those as explicit free cash flows, run base NPV, then sweep the hurdle rate from 10% to 15%."

```bash
dcf init --dir .dcf-product
dcf assume set discount_rate 0.12
dcf assume set cash_flow_y1 1000000
dcf assume set cash_flow_y5 3000000
dcf verify
dcf run --scenario base
dcf sensitivity --scenario base --over discount_rate
```

Output: a base NPV and sensitivity table for the hurdle-rate decision.

### Comparing acquisition scenarios
<!-- id: dcf/example-acquisition-scenarios -->

```bash
dcf init
dcf assume set revenue 25000000
dcf assume set revenue_growth 0.08
dcf assume set ebitda_margin 0.22
dcf scenario create downside
dcf scenario set downside revenue_growth 0.03
dcf scenario create upside
dcf scenario set upside revenue_growth 0.12
dcf run --scenario downside
dcf run --scenario upside
dcf scenario compare downside upside
```

Output: side-by-side value estimates with assumptions traceable through the log.

## Quick command reference
<!-- id: dcf/commands -->

For full options, run `dcf <subcommand> --help`.

| Command | Purpose |
|---|---|
| `dcf init` | Initialize a valuation project. |
| `dcf assume set/list/get/history` | Manage base assumptions and their history. |
| `dcf scenario create/set/rebase/list/show/compare` | Define and compare scenario overrides. |
| `dcf run` | Compute a valuation for a scenario. |
| `dcf show` | Display saved run or model information. |
| `dcf sensitivity` | Sweep assumptions and report value movement. |
| `dcf proposal ...` | Manage reviewed assumption-change sessions. |
| `dcf verify` | Validate model completeness and consistency. |
| `dcf log` | Inspect the append-only audit log. |
| `dcf import` / `export` | Move assumptions/results in or out of the project. |

## Common pitfalls
<!-- id: dcf/pitfalls -->

- Terminal value often dominates the answer; always show terminal-value share or a terminal-method comparison.
- A precise WACC estimate can create false confidence; use sensitivity when the rate is not externally fixed.
- Mixing enterprise and equity value assumptions causes double counting; treat cash/debt adjustments explicitly.
- Scenario names should represent coherent worlds, not single-parameter tweaks better handled by sensitivity.

## Cross-references
<!-- id: dcf/xrefs -->

- Downstream: feed monetary value or risk-adjusted NPV into [mcda](#mcda/mcda) when the decision has nonfinancial criteria.
- Adjacent methods: [raiffa](#raiffa/raiffa) for staged uncertainty and value of information; [premortem](#premortem/premortem) to stress-test assumptions before investment approval.
- Reporting: use [gutenberg](#gutenberg/gutenberg) and [tufte](#tufte/tufte) for final report compilation and plot QA.

## State contract
<!-- id: dcf/state -->

The DCF project directory stores append-only events plus derived valuation artifacts. The event log is authoritative for assumptions, scenarios, proposal actions, and runs; exported workbooks and rendered summaries are downstream products. Agents should use CLI commands for mutation and inspect logs/results for recovery.

## JSON output and error codes
<!-- id: dcf/json -->

dcf uses JSON output via `--format json`. Treat validation failures as recoverable input problems: inspect `errors`, fix missing or inconsistent assumptions, run `dcf verify`, then rerun valuation commands.
