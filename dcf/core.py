from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .store import (
    DcfError,
    DcfRepo,
    IntegrityError,
    ModelError,
    file_ts,
    iso_ts,
    load_json,
    next_seq,
    parse_value,
    parse_years,
    sha256_bytes,
    sha256_file,
    write_json,
)


def init_project(repo: DcfRepo, args: Any) -> dict[str, Any]:
    repo.init()
    now = iso_ts()
    config = {
        "version": "1.0",
        "company": args.company,
        "created_at": now,
        "author": args.author,
        "currency": args.currency,
        "fiscal_year_end": args.fiscal_year_end,
        "projection_years": args.years,
    }
    config_path = repo.root / "config.json"
    write_json(config_path, config)
    repo.append_log({"event": "init", "author": args.author, "company": args.company}, config_path)
    scenario = {
        "seq": 1,
        "name": "base",
        "created_at": now,
        "updated_at": now,
        "base_version": 0,
        "provenance": {"source": "scenario", "session_id": None, "proposal_id": None, "participant_id": None},
        "overrides": [],
        "rebase_history": [],
    }
    scenario_path = repo.root / "scenarios" / f"0001_{file_ts()}_base.json"
    write_json(scenario_path, scenario)
    repo.append_log({"event": "scenario_create", "author": args.author, "name": "base", "seq": 1}, scenario_path)
    return config


def set_assumption(repo: DcfRepo, key: str, value: str, years: str | None, note: str | None, author: str) -> dict[str, Any]:
    repo.ensure_exists()
    records = repo.assumption_records()
    seq = next_seq(repo.json_files("assumptions"))
    latest_for_key = [
        r
        for r in records
        if r.get("key") == key and r.get("years") == parse_years(years)
    ]
    record = {
        "seq": seq,
        "base_version": repo.current_base_version() + 1,
        "timestamp": iso_ts(),
        "author": author,
        "key": key,
        "value": parse_value(value),
    }
    parsed_years = parse_years(years)
    if parsed_years:
        record["years"] = parsed_years
    if note:
        record["note"] = note
    if latest_for_key:
        record["supersedes"] = max(int(r["seq"]) for r in latest_for_key)
    path = repo.root / "assumptions" / f"{seq:04d}_{file_ts()}.json"
    write_json(path, record)
    repo.append_log({"event": "assume_set", "author": author, "key": key, "value": record["value"], "seq": seq}, path)
    return record


def resolved_base(repo: DcfRepo, base_version: int | None = None) -> dict[str, Any]:
    records = repo.assumption_records()
    if base_version is not None:
        records = [r for r in records if int(r["base_version"]) <= base_version]
    records = sorted(records, key=lambda r: int(r["seq"]))
    scalars: dict[str, Any] = {}
    year_values: dict[str, dict[int, Any]] = {}
    for record in records:
        key = record["key"]
        if "years" in record:
            per_year = year_values.setdefault(key, {})
            for year in record["years"]:
                per_year[int(year)] = record["value"]
        else:
            scalars[key] = record["value"]
    resolved = dict(scalars)
    for key, values in year_values.items():
        max_year = max(values)
        fallback = scalars.get(key)
        resolved[key] = [values.get(year, fallback) for year in range(1, max_year + 1)]
    return resolved


def scenario_overrides_to_inputs(inputs: dict[str, Any], overrides: list[dict[str, Any]]) -> dict[str, Any]:
    resolved = dict(inputs)
    for override in overrides:
        key = override["key"]
        if "years" in override:
            existing = resolved.get(key)
            max_year = max(int(y) for y in override["years"])
            if isinstance(existing, list):
                values = list(existing)
            else:
                values = [existing for _ in range(max_year)]
            while len(values) < max_year:
                values.append(existing if not isinstance(existing, list) else None)
            for year in override["years"]:
                values[int(year) - 1] = override["value"]
            resolved[key] = values
        else:
            resolved[key] = override["value"]
    return resolved


def resolved_scenario(repo: DcfRepo, name: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if name == "base":
        return resolved_base(repo), None
    scenario = repo.latest_scenario(name)
    if not scenario:
        raise DcfError(f"unknown scenario: {name}")
    base = resolved_base(repo, int(scenario["base_version"]))
    return scenario_overrides_to_inputs(base, scenario.get("overrides", [])), scenario


def create_scenario(repo: DcfRepo, name: str, source: str | None, author: str) -> dict[str, Any]:
    repo.ensure_exists()
    if repo.latest_scenario(name):
        raise DcfError(f"scenario already exists: {name}")
    source_record = repo.latest_scenario(source) if source else None
    if source and not source_record:
        raise DcfError(f"unknown scenario: {source}")
    seq = next_seq(repo.json_files("scenarios"))
    now = iso_ts()
    record = {
        "seq": seq,
        "name": name,
        "created_at": now,
        "updated_at": now,
        "base_version": repo.current_base_version(),
        "provenance": {"source": "scenario", "session_id": None, "proposal_id": None, "participant_id": None},
        "overrides": list(source_record.get("overrides", [])) if source_record else [],
        "rebase_history": [],
    }
    path = repo.root / "scenarios" / f"{seq:04d}_{file_ts()}_{name}.json"
    write_json(path, record)
    repo.append_log({"event": "scenario_create", "author": author, "name": name, "seq": seq}, path)
    return record


def set_scenario(repo: DcfRepo, name: str, key: str, value: str, years: str | None, author: str) -> dict[str, Any]:
    repo.ensure_exists()
    current = repo.latest_scenario(name)
    if not current:
        raise DcfError(f"unknown scenario: {name}")
    seq = next_seq(repo.json_files("scenarios"))
    overrides = [o for o in current.get("overrides", []) if not (o["key"] == key and o.get("years") == parse_years(years))]
    override = {"key": key, "value": parse_value(value)}
    parsed_years = parse_years(years)
    if parsed_years:
        override["years"] = parsed_years
    overrides.append(override)
    record = dict(current)
    record["seq"] = seq
    record["updated_at"] = iso_ts()
    record["overrides"] = overrides
    path = repo.root / "scenarios" / f"{seq:04d}_{file_ts()}_{name}.json"
    write_json(path, record)
    repo.append_log({"event": "scenario_set", "author": author, "name": name, "key": key, "seq": seq}, path)
    return record


def rebase_scenario(repo: DcfRepo, name: str, author: str, note: str | None = None) -> dict[str, Any]:
    current = repo.latest_scenario(name)
    if not current:
        raise DcfError(f"unknown scenario: {name}")
    old_version = int(current["base_version"])
    new_version = repo.current_base_version()
    seq = next_seq(repo.json_files("scenarios"))
    record = dict(current)
    record["seq"] = seq
    record["updated_at"] = iso_ts()
    record["base_version"] = new_version
    history = list(current.get("rebase_history", []))
    history.append({"from_version": old_version, "to_version": new_version, "timestamp": iso_ts(), "author": author, "note": note})
    record["rebase_history"] = history
    path = repo.root / "scenarios" / f"{seq:04d}_{file_ts()}_{name}.json"
    write_json(path, record)
    repo.append_log({"event": "scenario_rebase", "author": author, "name": name, "seq": seq}, path)
    return record


def list_scenarios(repo: DcfRepo) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in repo.scenario_records():
        name = record["name"]
        if name not in latest or int(record["seq"]) > int(latest[name]["seq"]):
            latest[name] = record
    current_base = repo.current_base_version()
    rows = []
    for name, record in sorted(latest.items()):
        base_version = int(record["base_version"])
        rows.append({
            "name": name,
            "base_version": base_version,
            "current_base_version": current_base,
            "status": "up to date" if base_version == current_base or name == "base" else "rebase available",
        })
    return rows


def value_series(value: Any, years: int) -> list[float]:
    if isinstance(value, list):
        if not value:
            return [0.0] * years
        series = [float(v) for v in value]
        while len(series) < years:
            series.append(series[-1])
        return series[:years]
    return [float(value)] * years


def get_series(inputs: dict[str, Any], key: str, years: int, default: float = 0.0) -> list[float]:
    return value_series(inputs.get(key, default), years)


def calculate_dcf(inputs: dict[str, Any], projection_years: int) -> dict[str, Any]:
    required = ["revenue.initial", "revenue.growth_rate", "margins.ebit", "tax_rate", "capex.pct_revenue", "wacc"]
    missing = [key for key in required if key not in inputs or inputs[key] is None]
    if missing:
        raise ModelError(f"missing required assumptions: {', '.join(missing)}")
    wacc = float(inputs["wacc"])
    has_terminal_growth = inputs.get("terminal.growth_rate") is not None
    has_exit_multiple = inputs.get("terminal.exit_multiple") is not None
    if has_terminal_growth and has_exit_multiple:
        raise ModelError("terminal.growth_rate and terminal.exit_multiple are mutually exclusive")
    terminal_growth = float(inputs.get("terminal.growth_rate", 0.0) or 0.0)
    exit_multiple = float(inputs.get("terminal.exit_multiple", 0.0) or 0.0)
    if has_terminal_growth and terminal_growth >= wacc:
        raise ModelError("terminal.growth_rate must be lower than wacc")
    revenue = float(inputs["revenue.initial"])
    growth = get_series(inputs, "revenue.growth_rate", projection_years)
    ebit_margin = get_series(inputs, "margins.ebit", projection_years)
    tax_rate = get_series(inputs, "tax_rate", projection_years)
    capex_pct = get_series(inputs, "capex.pct_revenue", projection_years)
    da_pct = get_series(inputs, "depreciation.pct_revenue", projection_years, default=0.0)
    nwc_pct = get_series(inputs, "working_capital.pct_revenue", projection_years, default=0.0)
    free_cash_flows = []
    income_statement = []
    cash_flow_statement = []
    pv_total = 0.0
    last_fcf = 0.0
    last_ebitda = 0.0
    previous_nwc = revenue * nwc_pct[0] if nwc_pct else 0.0
    for idx in range(projection_years):
        revenue *= 1.0 + growth[idx]
        depreciation = revenue * da_pct[idx]
        ebit = revenue * ebit_margin[idx]
        ebitda = ebit + depreciation
        nopat = ebit * (1.0 - tax_rate[idx])
        capex = revenue * capex_pct[idx]
        nwc = revenue * nwc_pct[idx]
        change_nwc = nwc - previous_nwc
        fcf = nopat + depreciation - capex - change_nwc
        pv = fcf / ((1.0 + wacc) ** (idx + 1))
        free_cash_flows.append({
            "year": idx + 1,
            "revenue": round(revenue, 2),
            "ebitda": round(ebitda, 2),
            "ebit": round(ebit, 2),
            "nopat": round(nopat, 2),
            "depreciation": round(depreciation, 2),
            "capex": round(capex, 2),
            "change_nwc": round(change_nwc, 2),
            "fcf": round(fcf, 2),
            "pv": round(pv, 2),
        })
        income_statement.append({
            "year": idx + 1,
            "revenue": round(revenue, 2),
            "ebitda": round(ebitda, 2),
            "depreciation": round(depreciation, 2),
            "ebit": round(ebit, 2),
            "tax": round(ebit * tax_rate[idx], 2),
            "nopat": round(nopat, 2),
        })
        cash_flow_statement.append({
            "year": idx + 1,
            "nopat": round(nopat, 2),
            "depreciation": round(depreciation, 2),
            "capex": round(capex, 2),
            "change_nwc": round(change_nwc, 2),
            "free_cash_flow": round(fcf, 2),
        })
        pv_total += pv
        last_fcf = fcf
        last_ebitda = ebitda
        previous_nwc = nwc
    if has_exit_multiple:
        terminal_method = "exit_multiple"
        terminal_value = last_ebitda * exit_multiple
    else:
        terminal_method = "perpetuity_growth"
        terminal_value = last_fcf * (1.0 + terminal_growth) / (wacc - terminal_growth)
    terminal_pv = terminal_value / ((1.0 + wacc) ** projection_years)
    enterprise_value = pv_total + terminal_pv
    net_debt = float(inputs.get("net_debt", 0.0))
    shares = float(inputs.get("shares_outstanding", 1.0))
    equity_value = enterprise_value - net_debt
    return {
        "enterprise_value": round(enterprise_value, 2),
        "equity_value": round(equity_value, 2),
        "implied_share_price": round(equity_value / shares, 2),
        "terminal_value": round(terminal_value, 2),
        "terminal_method": terminal_method,
        "terminal_value_pct": round(terminal_pv / enterprise_value, 4) if enterprise_value else 0,
        "projection_years": projection_years,
        "free_cash_flows": free_cash_flows,
        "income_statement": income_statement,
        "balance_sheet": {},
        "cash_flow_statement": cash_flow_statement,
    }


def metric_for_inputs(inputs: dict[str, Any], projection_years: int, metric: str) -> float:
    outputs = calculate_dcf(inputs, projection_years)
    if metric not in outputs:
        raise DcfError(f"unsupported metric: {metric}")
    return float(outputs[metric])


def scenario_comparison(repo: DcfRepo, names: list[str], run: bool = False, metric: str = "implied_share_price") -> dict[str, Any]:
    config = load_json(repo.root / "config.json")
    projection_years = int(config.get("projection_years", 10))
    scenarios = {name: resolved_scenario(repo, name)[0] for name in names}
    keys = sorted({key for inputs in scenarios.values() for key in inputs})
    rows = []
    for key in keys:
        values = {name: scenarios[name].get(key) for name in names}
        if len({json.dumps(value, sort_keys=True) for value in values.values()}) > 1:
            rows.append({"key": key, "values": values})
    valuation = None
    if run:
        valuation = {}
        base_value = None
        for name, inputs in scenarios.items():
            value = metric_for_inputs(inputs, projection_years, metric)
            if base_value is None:
                base_value = value
            valuation[name] = {metric: value, "delta_vs_first": round(value - base_value, 2)}
    return {"scenarios": names, "differences": rows, "valuation": valuation}


def sensitivity_grid_for_inputs(
    inputs: dict[str, Any],
    projection_years: int,
    key_a: str,
    values_a: list[float],
    key_b: str,
    values_b: list[float],
    metric: str,
) -> dict[str, Any]:
    rows = []
    for value_a in values_a:
        row = {"key": key_a, "value": value_a, "values": []}
        for value_b in values_b:
            trial = dict(inputs)
            trial[key_a] = value_a
            trial[key_b] = value_b
            row["values"].append(round(metric_for_inputs(trial, projection_years, metric), 2))
        rows.append(row)
    return {"key_a": key_a, "values_a": values_a, "key_b": key_b, "values_b": values_b, "metric": metric, "rows": rows}


def parse_range(raw: str | None, current: float, key: str) -> list[float]:
    if raw:
        start, end, steps = raw.split(":", 2)
        start_f = float(start)
        end_f = float(end)
        steps_i = int(steps)
    elif key == "wacc":
        start_f, end_f, steps_i = current - 0.02, current + 0.02, 5
    elif key == "terminal.growth_rate":
        start_f, end_f, steps_i = 0.01, 0.04, 5
    elif key == "revenue.growth_rate":
        start_f, end_f, steps_i = current - 0.03, current + 0.03, 5
    else:
        start_f, end_f, steps_i = current * 0.8, current * 1.2, 5
    if steps_i < 2:
        return [round(start_f, 6)]
    step = (end_f - start_f) / (steps_i - 1)
    return [round(start_f + step * idx, 6) for idx in range(steps_i)]


def sensitivity_analysis(
    repo: DcfRepo,
    scenario: str,
    key_a: str,
    range_a: str | None,
    key_b: str,
    range_b: str | None,
    metric: str,
) -> dict[str, Any]:
    config = load_json(repo.root / "config.json")
    projection_years = int(config.get("projection_years", 10))
    inputs, _ = resolved_scenario(repo, scenario)
    current_a = value_series(inputs.get(key_a, 0), 1)[0]
    current_b = value_series(inputs.get(key_b, 0), 1)[0]
    return sensitivity_grid_for_inputs(
        inputs,
        projection_years,
        key_a,
        parse_range(range_a, current_a, key_a),
        key_b,
        parse_range(range_b, current_b, key_b),
        metric,
    )


def run_model(repo: DcfRepo, scenario: str, tag: str | None, author: str, proposal: dict[str, Any] | None = None) -> dict[str, Any]:
    repo.ensure_exists()
    config = load_json(repo.root / "config.json")
    if proposal:
        inputs = scenario_overrides_to_inputs(resolved_base(repo, int(proposal["base_version"])), proposal.get("overrides", []))
        scenario_name = f"proposal:{proposal['proposal_id']}"
        scenario_seq = proposal.get("scenario_seq")
    else:
        inputs, scenario_record = resolved_scenario(repo, scenario)
        scenario_name = scenario
        scenario_seq = None if scenario_record is None else scenario_record["seq"]
    outputs = calculate_dcf(inputs, int(config.get("projection_years", 10)))
    seq = next_seq(repo.json_files("runs"), prefix="r")
    run_id = f"r{seq:03d}"
    record = {
        "id": run_id,
        "timestamp": iso_ts(),
        "author": author,
        "tag": tag,
        "scenario": scenario_name,
        "assumption_seq": repo.latest_assumption_seq(),
        "scenario_seq": scenario_seq,
        "base_version": repo.current_base_version(),
        "inputs": inputs,
        "outputs": outputs,
    }
    path = repo.root / "runs" / f"{run_id}_{file_ts()}.json"
    write_json(path, record)
    repo.append_log({"event": "run", "author": author, "run_id": run_id, "scenario": scenario_name, "tag": tag}, path)
    return record


def create_proposal_session(repo: DcfRepo, participants: list[str], label: str | None, run_id: str | None, author: str) -> dict[str, Any]:
    repo.ensure_exists()
    sessions_root = repo.root / "proposals" / "sessions"
    seq = next_seq([p for p in sessions_root.glob("s*") if p.is_dir()], prefix="s")
    session_id = f"s{seq:03d}"
    path = sessions_root / f"{session_id}_{file_ts()}"
    path.mkdir(parents=True)
    manifest = {
        "session_id": session_id,
        "timestamp": iso_ts(),
        "label": label,
        "model_run": run_id,
        "participants": [{"id": p, "type": "human", "display_name": p} for p in participants],
        "status": "open",
        "consensus_proposal_id": None,
    }
    manifest_path = path / "manifest.json"
    write_json(manifest_path, manifest)
    repo.append_log({"event": "proposal_session", "author": author, "session_id": session_id, "participants": participants}, manifest_path)
    return manifest


def find_session_dir(repo: DcfRepo, session_id: str) -> Path:
    matches = sorted((repo.root / "proposals" / "sessions").glob(f"{session_id}_*"))
    if not matches:
        raise DcfError(f"unknown proposal session: {session_id}")
    return matches[-1]


def proposal_files(session_dir: Path) -> list[Path]:
    return sorted((session_dir / "proposals").glob("*.json")) if (session_dir / "proposals").exists() else []


def load_proposals(session_dir: Path) -> list[dict[str, Any]]:
    return [load_json(path) for path in proposal_files(session_dir)]


def submit_proposal(repo: DcfRepo, args: Any, author: str) -> dict[str, Any]:
    session_dir = find_session_dir(repo, args.session)
    proposals_dir = session_dir / "proposals"
    proposals_dir.mkdir(exist_ok=True)
    seq = next_seq(proposal_files(session_dir), prefix="p")
    proposal_id = f"p{seq:03d}"
    overrides = []
    rationales = dict(item.split("=", 1) for item in (args.rationale or []))
    if args.from_scenario:
        scenario = repo.latest_scenario(args.from_scenario)
        if not scenario:
            raise DcfError(f"unknown scenario: {args.from_scenario}")
        overrides.extend(scenario.get("overrides", []))
        scenario_seq = scenario["seq"]
        base_version = scenario["base_version"]
    else:
        scenario_seq = None
        base_version = repo.current_base_version()
    for item in args.set or []:
        key, raw = item.split("=", 1)
        override = {"key": key, "value": parse_value(raw)}
        if key in rationales:
            override["rationale"] = rationales[key]
        overrides = [o for o in overrides if o["key"] != key]
        overrides.append(override)
    record = {
        "proposal_id": proposal_id,
        "timestamp": iso_ts(),
        "participant_id": args.participant,
        "participant_type": args.participant_type,
        "label": args.label,
        "base_version": base_version,
        "scenario_seq": scenario_seq,
        "overrides": overrides,
        "source": {"kind": args.participant_type, "notes": args.source or []},
    }
    path = proposals_dir / f"{proposal_id}_{file_ts()}.json"
    write_json(path, record)
    repo.append_log({"event": "proposal_submit", "author": author, "session_id": args.session, "proposal_id": proposal_id}, path)
    return record


def get_proposal(repo: DcfRepo, session_id: str, proposal_id: str | None) -> dict[str, Any]:
    session_dir = find_session_dir(repo, session_id)
    proposals = load_proposals(session_dir)
    if proposal_id is None:
        manifest = load_json(session_dir / "manifest.json")
        proposal_id = manifest.get("consensus_proposal_id")
    for proposal in proposals:
        if proposal["proposal_id"] == proposal_id:
            return proposal
    raise DcfError(f"unknown proposal: {proposal_id}")


def compare_proposals(repo: DcfRepo, session_id: str, proposal_ids: list[str] | None, metric: str, run: bool, author: str) -> list[dict[str, Any]]:
    session_dir = find_session_dir(repo, session_id)
    proposals = load_proposals(session_dir)
    if proposal_ids:
        proposals = [p for p in proposals if p["proposal_id"] in proposal_ids]
    rows = []
    first_value = None
    for proposal in proposals:
        row = {"proposal_id": proposal["proposal_id"], "participant_id": proposal["participant_id"], "label": proposal.get("label")}
        if run:
            record = run_model(repo, "base", f"proposal {proposal['proposal_id']}", author, proposal=proposal)
            row["run_id"] = record["id"]
            row[metric] = record["outputs"][metric]
            if first_value is None:
                first_value = float(record["outputs"][metric])
            row["delta_vs_first"] = round(float(record["outputs"][metric]) - first_value, 2)
        rows.append(row)
    return rows


def promote_proposal(repo: DcfRepo, session_id: str, proposal_id: str, scenario_name: str, author: str) -> dict[str, Any]:
    proposal = get_proposal(repo, session_id, proposal_id)
    seq = next_seq(repo.json_files("scenarios"))
    now = iso_ts()
    record = {
        "seq": seq,
        "name": scenario_name,
        "created_at": now,
        "updated_at": now,
        "base_version": proposal["base_version"],
        "provenance": {
            "source": "proposal",
            "session_id": session_id,
            "proposal_id": proposal_id,
            "participant_id": proposal["participant_id"],
        },
        "overrides": proposal.get("overrides", []),
        "rebase_history": [],
    }
    path = repo.root / "scenarios" / f"{seq:04d}_{file_ts()}_{scenario_name}.json"
    write_json(path, record)
    repo.append_log({"event": "proposal_promote", "author": author, "session_id": session_id, "proposal_id": proposal_id, "scenario": scenario_name}, path)
    return record


def import_file(repo: DcfRepo, statement: str, source: str, year: int, fmt: str, author: str) -> dict[str, Any]:
    repo.ensure_exists()
    seq = next_seq(list((repo.root / "imports").glob("*")))
    source_path = Path(source)
    if not source_path.exists():
        raise DcfError(f"import file not found: {source}")
    raw_path = repo.root / "imports" / f"{seq:04d}_{file_ts()}_{statement}.{fmt}"
    shutil.copyfile(source_path, raw_path)
    repo.append_log({"event": "import_raw", "author": author, "statement": statement, "year": year}, raw_path)
    historical = {
        "seq": seq,
        "timestamp": iso_ts(),
        "author": author,
        "statement": statement,
        "fiscal_year": year,
        "source_file": repo.rel(raw_path),
        "import_map_seq": None,
        "values": {},
    }
    hist_path = repo.root / "historicals" / f"{seq:04d}_{file_ts()}_{statement}.json"
    write_json(hist_path, historical)
    repo.append_log({"event": "import_historical", "author": author, "statement": statement, "year": year}, hist_path)
    return historical


def verify_repo(repo: DcfRepo) -> dict[str, Any]:
    repo.ensure_exists()
    issues: list[dict[str, str]] = []
    logged_paths: set[str] = set()
    previous_hash = None
    for lineno, line in enumerate(repo.log_path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append({"type": "invalid_log_json", "line": str(lineno), "detail": str(exc)})
            continue
        if event.get("prev_entry_hash") != previous_hash:
            issues.append({"type": "log_hash_chain", "line": str(lineno)})
        previous_hash = sha256_bytes(line.encode("utf-8"))
        artifact = event.get("artifact")
        if artifact:
            rel_path = artifact["path"]
            logged_paths.add(rel_path)
            path = repo.root / rel_path
            if not path.exists():
                issues.append({"type": "missing_artifact", "path": rel_path})
            elif sha256_file(path) != artifact["sha256"]:
                issues.append({"type": "hash_mismatch", "path": rel_path})
    for path in repo.root.rglob("*"):
        if path.is_dir() or path == repo.log_path:
            continue
        rel = repo.rel(path)
        if rel.endswith(".lock"):
            continue
        if rel not in logged_paths:
            issues.append({"type": "unexpected_file", "path": rel})
    result = {"clean": not issues, "issues": issues}
    if issues:
        raise IntegrityError(json.dumps(result))
    return result
