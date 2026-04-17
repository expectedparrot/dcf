from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from .core import (
    compare_proposals,
    create_proposal_session,
    create_scenario,
    get_proposal,
    import_file,
    init_project,
    list_scenarios,
    promote_proposal,
    rebase_scenario,
    resolved_base,
    resolved_scenario,
    run_model,
    scenario_comparison,
    set_assumption,
    set_scenario,
    sensitivity_analysis,
    submit_proposal,
    verify_repo,
)
from .excel import export_excel
from .store import DcfError, DcfRepo, IntegrityError, load_json


def print_data(data: Any, json_format: bool = False) -> None:
    if json_format:
        print(json.dumps(data, indent=2, sort_keys=True))
    elif isinstance(data, list):
        for row in data:
            print(row)
    elif isinstance(data, dict):
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(data)


def author_from(args: argparse.Namespace) -> str:
    return args.author or os.environ.get("USER") or "unknown"


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dir", dest="dcf_dir")
    parser.add_argument("--author")
    parser.add_argument("--format", choices=["json"])
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--no-color", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dcf")
    add_common(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--company", required=True)
    init.add_argument("--author")
    init.add_argument("--currency", default="USD")
    init.add_argument("--fiscal-year-end", default="12-31")
    init.add_argument("--years", type=int, default=10)

    assume = sub.add_parser("assume")
    assume_sub = assume.add_subparsers(dest="assume_command", required=True)
    assume_set = assume_sub.add_parser("set")
    assume_set.add_argument("key")
    assume_set.add_argument("value")
    assume_set.add_argument("--years")
    assume_set.add_argument("--note")
    assume_set.add_argument("--author")
    assume_list = assume_sub.add_parser("list")
    assume_list.add_argument("--format", choices=["json"])
    assume_get = assume_sub.add_parser("get")
    assume_get.add_argument("key")
    assume_get.add_argument("--format", choices=["json"])
    assume_history = assume_sub.add_parser("history")
    assume_history.add_argument("key")
    assume_history.add_argument("--format", choices=["json"])

    scenario = sub.add_parser("scenario")
    scenario_sub = scenario.add_subparsers(dest="scenario_command", required=True)
    scenario_create = scenario_sub.add_parser("create")
    scenario_create.add_argument("name")
    scenario_create.add_argument("--from", dest="source")
    scenario_create.add_argument("--author")
    scenario_set = scenario_sub.add_parser("set")
    scenario_set.add_argument("name")
    scenario_set.add_argument("key")
    scenario_set.add_argument("value")
    scenario_set.add_argument("--years")
    scenario_set.add_argument("--author")
    scenario_rebase = scenario_sub.add_parser("rebase")
    scenario_rebase.add_argument("name")
    scenario_rebase.add_argument("--note")
    scenario_rebase.add_argument("--author")
    scenario_list = scenario_sub.add_parser("list")
    scenario_list.add_argument("--format", choices=["json"])
    scenario_show = scenario_sub.add_parser("show")
    scenario_show.add_argument("name")
    scenario_show.add_argument("--format", choices=["json"])
    scenario_compare = scenario_sub.add_parser("compare")
    scenario_compare.add_argument("names", nargs="+")
    scenario_compare.add_argument("--run", action="store_true")
    scenario_compare.add_argument("--metric", default="implied_share_price")
    scenario_compare.add_argument("--format", choices=["json"])

    run = sub.add_parser("run")
    run.add_argument("--scenario", default="base")
    run.add_argument("--scenarios", nargs="+")
    run.add_argument("--tag")
    run.add_argument("--author")
    run.add_argument("--format", choices=["json"])

    show = sub.add_parser("show")
    show.add_argument("--run")
    show.add_argument("--scenario")
    show.add_argument("--format", choices=["json"])

    sensitivity = sub.add_parser("sensitivity")
    sensitivity.add_argument("terms", nargs="+")
    sensitivity.add_argument("--scenario", default="base")
    sensitivity.add_argument("--metric", default="enterprise_value")
    sensitivity.add_argument("--format", choices=["json"])

    proposal = sub.add_parser("proposal")
    proposal_sub = proposal.add_subparsers(dest="proposal_command", required=True)
    proposal_session = proposal_sub.add_parser("session")
    proposal_session_sub = proposal_session.add_subparsers(dest="proposal_session_command", required=True)
    proposal_session_create = proposal_session_sub.add_parser("create")
    proposal_session_create.add_argument("--participant", action="append", default=[])
    proposal_session_create.add_argument("--label")
    proposal_session_create.add_argument("--run")
    proposal_session_create.add_argument("--author")
    proposal_session_create.add_argument("--format", choices=["json"])
    proposal_submit = proposal_sub.add_parser("submit")
    proposal_submit.add_argument("--session", required=True)
    proposal_submit.add_argument("--participant", required=True)
    proposal_submit.add_argument("--participant-type", default="human", choices=["human", "external", "system"])
    proposal_submit.add_argument("--label")
    proposal_submit.add_argument("--from-scenario")
    proposal_submit.add_argument("--set", action="append", default=[])
    proposal_submit.add_argument("--rationale", action="append", default=[])
    proposal_submit.add_argument("--source", action="append", default=[])
    proposal_submit.add_argument("--author")
    proposal_submit.add_argument("--format", choices=["json"])
    proposal_show = proposal_sub.add_parser("show")
    proposal_show.add_argument("--session", required=True)
    proposal_show.add_argument("--proposal")
    proposal_show.add_argument("--format", choices=["json"])
    proposal_compare = proposal_sub.add_parser("compare")
    proposal_compare.add_argument("--session", required=True)
    proposal_compare.add_argument("--proposals", nargs="+")
    proposal_compare.add_argument("--metric", default="implied_share_price")
    proposal_compare.add_argument("--run", action="store_true")
    proposal_compare.add_argument("--author")
    proposal_compare.add_argument("--format", choices=["json"])
    proposal_run = proposal_sub.add_parser("run")
    proposal_run.add_argument("--session", required=True)
    proposal_run.add_argument("--proposal")
    proposal_run.add_argument("--tag")
    proposal_run.add_argument("--author")
    proposal_run.add_argument("--format", choices=["json"])
    proposal_promote = proposal_sub.add_parser("promote")
    proposal_promote.add_argument("--session", required=True)
    proposal_promote.add_argument("--proposal", required=True)
    proposal_promote.add_argument("--scenario", required=True)
    proposal_promote.add_argument("--author")
    proposal_promote.add_argument("--format", choices=["json"])

    verify = sub.add_parser("verify")
    verify.add_argument("--format", choices=["json"])

    log = sub.add_parser("log")
    log.add_argument("--format", choices=["json"])

    imp = sub.add_parser("import")
    imp.add_argument("statement", choices=["income-statement", "balance-sheet", "cash-flows"])
    imp.add_argument("file")
    imp.add_argument("--year", type=int, required=True)
    imp.add_argument("--format", default="csv", choices=["csv", "json"])
    imp.add_argument("--author")

    export = sub.add_parser("export")
    export.add_argument("format", choices=["excel"])
    export.add_argument("--scenario", default="base")
    export.add_argument("--out")
    export.add_argument("--format-json", action="store_true")

    return parser


def handle(args: argparse.Namespace) -> Any:
    repo = DcfRepo.discover(explicit=getattr(args, "dcf_dir", None))
    if args.command != "init" and repo.exists() and not getattr(args, "_locked", False):
        with repo.lock():
            setattr(args, "_locked", True)
            return handle(args)
    if args.command == "init":
        return init_project(repo, args)
    if args.command == "assume":
        if args.assume_command == "set":
            return set_assumption(repo, args.key, args.value, args.years, args.note, author_from(args))
        if args.assume_command == "list":
            return resolved_base(repo)
        if args.assume_command == "get":
            return {args.key: resolved_base(repo).get(args.key)}
        if args.assume_command == "history":
            return [r for r in repo.assumption_records() if r["key"] == args.key]
    if args.command == "scenario":
        if args.scenario_command == "create":
            return create_scenario(repo, args.name, args.source, author_from(args))
        if args.scenario_command == "set":
            return set_scenario(repo, args.name, args.key, args.value, args.years, author_from(args))
        if args.scenario_command == "rebase":
            return rebase_scenario(repo, args.name, author_from(args), args.note)
        if args.scenario_command == "list":
            return list_scenarios(repo)
        if args.scenario_command == "show":
            inputs, scenario = resolved_scenario(repo, args.name)
            return {"scenario": scenario, "inputs": inputs}
        if args.scenario_command == "compare":
            return scenario_comparison(repo, args.names, run=args.run, metric=args.metric)
    if args.command == "run":
        names = args.scenarios or [args.scenario]
        runs = [run_model(repo, name, args.tag, author_from(args)) for name in names]
        return runs[0] if len(runs) == 1 else runs
    if args.command == "show":
        if args.run:
            for record in repo.run_records():
                if record["id"] == args.run:
                    return record
            raise DcfError(f"unknown run: {args.run}")
        record = repo.latest_run(args.scenario)
        if not record:
            raise DcfError("no runs found")
        return record
    if args.command == "sensitivity":
        if len(args.terms) == 2:
            key_a, key_b = args.terms
            range_a = range_b = None
        elif len(args.terms) == 4:
            key_a, range_a, key_b, range_b = args.terms
        else:
            raise DcfError("usage: dcf sensitivity <key_a> [range_a] <key_b> [range_b]")
        return sensitivity_analysis(repo, args.scenario, key_a, range_a, key_b, range_b, args.metric)
    if args.command == "proposal":
        if args.proposal_command == "session":
            return create_proposal_session(repo, args.participant, args.label, args.run, author_from(args))
        if args.proposal_command == "submit":
            return submit_proposal(repo, args, author_from(args))
        if args.proposal_command == "show":
            if args.proposal:
                return get_proposal(repo, args.session, args.proposal)
            from .core import find_session_dir, load_proposals

            session_dir = find_session_dir(repo, args.session)
            return {"manifest": load_json(session_dir / "manifest.json"), "proposals": load_proposals(session_dir)}
        if args.proposal_command == "compare":
            return compare_proposals(repo, args.session, args.proposals, args.metric, args.run, author_from(args))
        if args.proposal_command == "run":
            proposal = get_proposal(repo, args.session, args.proposal)
            return run_model(repo, "base", args.tag, author_from(args), proposal=proposal)
        if args.proposal_command == "promote":
            return promote_proposal(repo, args.session, args.proposal, args.scenario, author_from(args))
    if args.command == "verify":
        return verify_repo(repo)
    if args.command == "log":
        repo.ensure_exists()
        return [json.loads(line) for line in repo.log_path.read_text(encoding="utf-8").splitlines() if line]
    if args.command == "import":
        return import_file(repo, args.statement, args.file, args.year, args.format, author_from(args))
    if args.command == "export":
        if args.format == "excel":
            path = export_excel(repo, args.scenario, args.out)
            return {"path": str(path), "scenario": args.scenario, "format": "excel"}
    raise DcfError("unhandled command")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        data = handle(args)
        json_format = getattr(args, "format", None) == "json" or getattr(args, "format_json", False)
        if not getattr(args, "quiet", False):
            print_data(data, json_format=json_format)
        return 0
    except IntegrityError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except DcfError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
