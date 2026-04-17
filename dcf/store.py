from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_DIRS = [
    "assumptions",
    "scenarios",
    "runs",
    "imports",
    "historicals",
    "import_maps",
    "proposals/sessions",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_ts(dt: datetime | None = None) -> str:
    return (dt or utc_now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def file_ts(dt: datetime | None = None) -> str:
    return (dt or utc_now()).strftime("%Y%m%d_%H%M%S")


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pretty_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pretty_json(data), encoding="utf-8")


def parse_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered == "null":
        return None
    try:
        if any(ch in raw for ch in ".eE"):
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def parse_years(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    years: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            years.extend(range(int(start), int(end) + 1))
        else:
            years.append(int(part))
    return sorted(set(years))


def next_seq(paths: list[Path], prefix: str = "") -> int:
    max_seq = 0
    for path in paths:
        name = path.name
        if prefix:
            if not name.startswith(prefix):
                continue
            seq_part = name[len(prefix) :].split("_", 1)[0]
        else:
            seq_part = name.split("_", 1)[0]
        try:
            max_seq = max(max_seq, int(seq_part))
        except ValueError:
            continue
    return max_seq + 1


@dataclass
class DcfRepo:
    root: Path

    @property
    def log_path(self) -> Path:
        return self.root / "log.jsonl"

    @classmethod
    def discover(cls, start: Path | None = None, explicit: str | None = None) -> "DcfRepo":
        if explicit:
            root = Path(explicit)
            if root.name != ".dcf":
                root = root / ".dcf"
            return cls(root)
        current = (start or Path.cwd()).resolve()
        for parent in [current, *current.parents]:
            candidate = parent / ".dcf"
            if candidate.exists():
                return cls(candidate)
        return cls(current / ".dcf")

    def exists(self) -> bool:
        return self.root.exists()

    def ensure_exists(self) -> None:
        if not self.exists():
            raise DcfError(f"no .dcf directory found at {self.root}")

    def init(self) -> None:
        if self.root.exists():
            raise DcfError(f"{self.root} already exists")
        self.root.mkdir(parents=True)
        for dirname in PROJECT_DIRS:
            (self.root / dirname).mkdir(parents=True, exist_ok=True)
        self.log_path.touch()

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def append_log(self, event: dict[str, Any], artifact: Path | None = None) -> None:
        event = dict(event)
        if artifact is not None:
            event["artifact"] = {"path": self.rel(artifact), "sha256": sha256_file(artifact)}
        event.setdefault("ts", iso_ts())
        event["prev_entry_hash"] = self.last_log_hash()
        line = canonical_json(event)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    @contextmanager
    def lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / ".lock"
        fd: int | None = None
        deadline = time.monotonic() + 10
        while fd is None:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode("utf-8"))
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise DcfError(f"timed out waiting for lock: {lock_path}")
                time.sleep(0.05)
        try:
            yield
        finally:
            if fd is not None:
                os.close(fd)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def last_log_hash(self) -> str | None:
        if not self.log_path.exists():
            return None
        previous: str | None = None
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if line:
                previous = sha256_bytes(line.encode("utf-8"))
        return previous

    def json_files(self, dirname: str) -> list[Path]:
        directory = self.root / dirname
        if not directory.exists():
            return []
        return sorted(directory.glob("*.json"))

    def assumption_records(self) -> list[dict[str, Any]]:
        return [load_json(path) for path in self.json_files("assumptions")]

    def scenario_records(self) -> list[dict[str, Any]]:
        return [load_json(path) for path in self.json_files("scenarios")]

    def run_records(self) -> list[dict[str, Any]]:
        return [load_json(path) for path in self.json_files("runs")]

    def current_base_version(self) -> int:
        records = self.assumption_records()
        return max((int(record.get("base_version", 0)) for record in records), default=0)

    def latest_assumption_seq(self) -> int | None:
        records = self.assumption_records()
        if not records:
            return None
        return max(int(record["seq"]) for record in records)

    def latest_scenario(self, name: str) -> dict[str, Any] | None:
        matches = [r for r in self.scenario_records() if r.get("name") == name]
        if not matches:
            return None
        return max(matches, key=lambda r: int(r["seq"]))

    def latest_run(self, scenario: str | None = None) -> dict[str, Any] | None:
        records = self.run_records()
        if scenario:
            records = [r for r in records if r.get("scenario") == scenario]
        if not records:
            return None
        return max(records, key=lambda r: r["id"])


class DcfError(Exception):
    exit_code = 1


class ModelError(DcfError):
    exit_code = 3


class IntegrityError(DcfError):
    exit_code = 2
