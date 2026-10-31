"""Run store (plan v2 §8.4).

Each run writes `data/cases/<case_id>/run-<n>/input.json`, `case.json` and
`brief.md` exactly once, reads them back, and only then writes `manifest.json`
with their SHA-256 hashes and `DELIVERED`. A missing manifest means the run was
not delivered; no partial run is ever presented as delivered.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from proofroom import config
from proofroom.errors import StoreError

log = logging.getLogger(__name__)

FILES = ("input.json", "case.json", "brief.md")
DEDUP_WINDOW_S = 600  # an identical request within 10 minutes returns the existing run

_case_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def case_id_for(domain: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", domain.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"cannot make a case id from {domain!r}")
    return slug


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_hash(input_obj: dict) -> str:
    return sha256_bytes(json.dumps(input_obj, sort_keys=True, ensure_ascii=False).encode())


def case_lock(case_id: str) -> threading.Lock:
    """One active run per case (in-process lock)."""
    with _locks_guard:
        return _case_locks.setdefault(case_id, threading.Lock())


@dataclass
class RunDir:
    case_id: str
    run: int
    path: Path

    @property
    def manifest_path(self) -> Path:
        return self.path / "manifest.json"


class Store:
    def __init__(self, root: Path | None = None, clock: Callable[[], float] = time.time):
        self.root = (root or config.DATA_DIR) / "cases"
        self._clock = clock

    def case_dir(self, case_id: str) -> Path:
        return self.root / case_id

    def runs(self, case_id: str) -> list[int]:
        d = self.case_dir(case_id)
        if not d.is_dir():
            return []
        out = []
        for p in d.iterdir():
            m = re.fullmatch(r"run-(\d+)", p.name)
            if m and p.is_dir():
                out.append(int(m.group(1)))
        return sorted(out)

    def new_run(self, case_id: str) -> RunDir:
        """Allocate run-<n+1>. mkdir(exist_ok=False) guards against two writers."""
        for _ in range(5):
            n = (self.runs(case_id) or [0])[-1] + 1
            path = self.case_dir(case_id) / f"run-{n}"
            try:
                path.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                continue
            except OSError as e:
                raise StoreError(f"cannot create run folder {path}: {e}") from e
            return RunDir(case_id, n, path)
        raise StoreError(f"could not allocate a run folder for {case_id}")

    def recent_identical(self, case_id: str, input_obj: dict) -> RunDir | None:
        """A DELIVERED run with the same request hash within the dedup window."""
        want = request_hash(input_obj)
        for n in reversed(self.runs(case_id)):
            rd = RunDir(case_id, n, self.case_dir(case_id) / f"run-{n}")
            man = read_manifest(rd)
            if not man or man.get("status") != "DELIVERED":
                continue
            if self._clock() - float(man.get("written_at", 0)) > DEDUP_WINDOW_S:
                return None
            if man.get("request_hash") == want:
                return rd
        return None

    def publish(self, rd: RunDir, input_obj: dict, case_obj: dict, brief_md: str,
                run_status: str = "DELIVERED", extra: dict[str, str | bytes] | None = None) -> dict:
        """Write the three files once, read them back, then write the manifest.

        `run_status` is the brief's own status (DELIVERED or NARROWED); the manifest's
        `delivery` is DELIVERED only after every file verified. Raises StoreError and
        leaves no manifest on any failure.
        """
        if rd.manifest_path.exists():
            raise StoreError(f"{rd.path} already has a manifest; runs are write-once")
        payloads = {
            "input.json": _dumps(input_obj),
            "case.json": _dumps(case_obj),
            "brief.md": brief_md.encode("utf-8"),
        }
        for name, text in (extra or {}).items():
            if name in payloads or "/" in name or name.startswith(".") or name == "manifest.json":
                raise StoreError(f"invalid extra file name {name!r}")
            payloads[name] = text if isinstance(text, bytes) else text.encode("utf-8")
        names = list(payloads)
        hashes: dict[str, str] = {}
        for name in names:
            data = payloads[name]
            path = rd.path / name
            try:
                with open(path, "xb") as f:  # exclusive create: written once
                    f.write(data)
            except OSError as e:
                raise StoreError(f"write failed for {name}: {e}") from e
            hashes[name] = sha256_bytes(data)

        for name in names:  # read back and verify before any manifest
            try:
                back = (rd.path / name).read_bytes()
            except OSError as e:
                raise StoreError(f"read-back failed for {name}: {e}") from e
            if sha256_bytes(back) != hashes[name]:
                raise StoreError(f"read-back hash mismatch for {name}")

        manifest = {
            "case_id": rd.case_id,
            "run": rd.run,
            "delivery": "DELIVERED",
            "status": "DELIVERED",
            "brief_status": run_status,
            "files": hashes,
            "request_hash": request_hash(input_obj),
            "written_at": self._clock(),
        }
        tmp = rd.path / "manifest.json.tmp"
        try:
            tmp.write_bytes(_dumps(manifest))
            tmp.replace(rd.manifest_path)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise StoreError(f"manifest write failed: {e}") from e
        log.info("published %s run-%d (%s)", rd.case_id, rd.run, run_status)
        return manifest


def _dumps(obj: object) -> bytes:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False).encode("utf-8")


def read_manifest(rd: RunDir) -> dict | None:
    try:
        return json.loads(rd.manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        log.warning("unreadable manifest in %s: %s", rd.path, e)
        return None


def verify_run(rd: RunDir) -> bool:
    """True only if the manifest says DELIVERED and every file still matches its hash."""
    man = read_manifest(rd)
    if not man or man.get("delivery") != "DELIVERED":
        return False
    for name, digest in (man.get("files") or {}).items():
        try:
            if sha256_bytes((rd.path / name).read_bytes()) != digest:
                return False
        except OSError:
            return False
    return set(FILES) <= set(man.get("files") or {})
