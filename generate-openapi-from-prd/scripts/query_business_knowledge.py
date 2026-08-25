#!/usr/bin/env python3
"""Query allowlisted business knowledge from a versioned Git cache."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from urllib.parse import urlsplit


DEFAULT_TTL_SECONDS = 900
SKILL_DIR = Path(__file__).resolve().parents[1]
MANIFEST_PATH = SKILL_DIR / "references" / "business-knowledge-sources.json"


@dataclass(frozen=True)
class DocumentConfig:
    id: str
    path: str
    authority: str


@dataclass(frozen=True)
class SourceConfig:
    id: str
    remote: str
    ref: str
    documents: dict[str, DocumentConfig]


@dataclass(frozen=True)
class Snapshot:
    commit: str
    commit_time: str
    freshness: str
    cache_age_seconds: int | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class Section:
    level: int
    heading: str
    normalized_heading: str
    start_line: int
    end_line: int
    body_start_line: int
    content: str
    own_content: str


class CliError(Exception):
    def __init__(self, exit_code: int, category: str, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.category = category
        self.message = message


class _CacheLock:
    def __init__(self, path: Path, timeout_seconds: float) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.acquired = False

    def __enter__(self) -> "_CacheLock":
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                self.path.mkdir()
                self.acquired = True
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise CliError(
                        5,
                        "cache",
                        "another process is updating the business knowledge cache",
                    )
                time.sleep(0.01)

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.acquired:
            self.path.rmdir()


class GitCache:
    def __init__(
        self,
        source: SourceConfig,
        cache_root: Path,
        *,
        lock_timeout_seconds: float = 30.0,
    ) -> None:
        self.source = source
        self.source_dir = cache_root / source.id
        self.repo_dir = self.source_dir / "repo.git"
        self.state_path = self.source_dir / "state.json"
        self.lock_path = self.source_dir / "update.lock"
        self.lock_timeout_seconds = lock_timeout_seconds

    def _load_state(self) -> dict[str, object]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(state["commit"], str) or not re.fullmatch(
                r"(?:[0-9a-f]{40}|[0-9a-f]{64})", state["commit"]
            ):
                raise TypeError
            if not isinstance(state["commit_time"], str):
                raise TypeError
            if not isinstance(state["last_refresh_epoch"], (int, float)):
                raise TypeError
            return state
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CliError(5, "cache", "business knowledge cache state is unreadable") from exc

    def _write_state(self, state: dict[str, object]) -> None:
        try:
            with tempfile.TemporaryDirectory(
                prefix="state.tmp-", dir=self.source_dir
            ) as temp_dir:
                staged_state = Path(temp_dir) / "state.json"
                staged_state.write_text(
                    json.dumps(state, ensure_ascii=True), encoding="ascii"
                )
                os.replace(staged_state, self.state_path)
        except OSError as exc:
            raise CliError(5, "cache", "unable to publish business knowledge cache state") from exc

    def _git(
        self,
        *arguments: str,
        network: bool = False,
        preserve_output: bool = False,
    ) -> str:
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(
            ["git", *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
        if result.returncode != 0:
            if network:
                raise CliError(3, "network", "unable to refresh business knowledge cache")
            raise CliError(5, "cache", "business knowledge cache is unreadable")
        return result.stdout if preserve_output else result.stdout.strip()

    def resolve(self, refresh: bool, offline: bool) -> Snapshot:
        if self.repo_dir.exists() and offline:
            state = self._load_state()
            age = max(0, int(time.time() - float(state["last_refresh_epoch"])))
            stale = age > DEFAULT_TTL_SECONDS
            warnings = (
                ("offline cache is older than the freshness threshold",)
                if stale
                else ()
            )
            return Snapshot(
                str(state["commit"]),
                str(state["commit_time"]),
                "stale" if stale else "fresh",
                age,
                warnings,
            )
        should_fetch = refresh
        if self.repo_dir.exists() and not refresh:
            state = self._load_state()
            age = max(0, int(time.time() - float(state["last_refresh_epoch"])))
            if age <= DEFAULT_TTL_SECONDS:
                return Snapshot(
                    str(state["commit"]),
                    str(state["commit_time"]),
                    "fresh",
                    age,
                    (),
                )
            should_fetch = True
        commit_ref = f"refs/heads/{self.source.ref}"
        if not self.repo_dir.exists() and offline:
            raise CliError(3, "network", "business knowledge cache is unavailable offline")
        self.source_dir.mkdir(parents=True, exist_ok=True)
        with _CacheLock(self.lock_path, self.lock_timeout_seconds):
            if not self.repo_dir.exists():
                with tempfile.TemporaryDirectory(
                    prefix="repo.tmp-", dir=self.source_dir
                ) as temp_dir:
                    staged_repo = Path(temp_dir) / "repo.git"
                    self._git(
                        "clone",
                        "--bare",
                        "--depth",
                        "1",
                        "--single-branch",
                        "--branch",
                        self.source.ref,
                        self.source.remote,
                        str(staged_repo),
                        network=True,
                    )
                    os.replace(staged_repo, self.repo_dir)
            elif should_fetch:
                remote_ref = f"refs/remotes/origin/{self.source.ref}"
                try:
                    self._git(
                        "--git-dir",
                        str(self.repo_dir),
                        "fetch",
                        "--depth",
                        "1",
                        "origin",
                        f"+refs/heads/{self.source.ref}:{remote_ref}",
                        network=True,
                    )
                except CliError:
                    if refresh:
                        raise
                    state = self._load_state()
                    age = max(0, int(time.time() - float(state["last_refresh_epoch"])))
                    return Snapshot(
                        str(state["commit"]),
                        str(state["commit_time"]),
                        "stale",
                        age,
                        ("refresh failed; using stale cached business knowledge",),
                    )
                commit_ref = remote_ref
            commit = self._git(
                "--git-dir",
                str(self.repo_dir),
                "rev-parse",
                commit_ref,
            )
            commit_time = self._git(
                "--git-dir",
                str(self.repo_dir),
                "show",
                "-s",
                "--format=%cI",
                commit,
            )
            state = {
                "commit": commit,
                "commit_time": commit_time,
                "last_refresh_epoch": time.time(),
            }
            self._write_state(state)
            return Snapshot(commit, commit_time, "fresh", 0, ())

    def read_document(self, snapshot: Snapshot, document: DocumentConfig) -> str:
        return self._git(
            "--git-dir",
            str(self.repo_dir),
            "show",
            f"{snapshot.commit}:{document.path}",
            preserve_output=True,
        )


def _validate_document_path(value: object) -> str:
    if not isinstance(value, str):
        raise CliError(2, "config", "document path must be a safe relative Markdown path")
    parts = value.split("/")
    unsafe = (
        not value
        or value.startswith("/")
        or "\\" in value
        or re.match(r"^[A-Za-z]:", value) is not None
        or any(part in {"", ".", ".."} for part in parts)
        or not value.lower().endswith(".md")
    )
    if unsafe:
        raise CliError(2, "config", "document path must be a safe relative Markdown path")
    return value


_HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_DECIMAL_HEADING_PREFIX = re.compile(r"^\d+(?:\.\d+)*(?:[、.．)]\s*|\s+)")
_CHINESE_HEADING_PREFIX = re.compile(r"^[一二三四五六七八九十百]+[、.．]\s*")


def _normalize_heading(heading: str) -> str:
    normalized = _DECIMAL_HEADING_PREFIX.sub("", heading.strip())
    normalized = _CHINESE_HEADING_PREFIX.sub("", normalized)
    return normalized.strip().casefold()


def parse_sections(text: str) -> list[Section]:
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []
    for line_number, line in enumerate(lines, start=1):
        match = _HEADING_PATTERN.match(line)
        if match:
            headings.append((line_number, len(match.group(1)), match.group(2).strip()))

    sections: list[Section] = []
    for index, (start_line, level, heading) in enumerate(headings):
        end_line = len(lines)
        for next_line, next_level, _ in headings[index + 1 :]:
            if next_level <= level:
                end_line = next_line - 1
                break
        own_end_line = headings[index + 1][0] - 1 if index + 1 < len(headings) else end_line
        body_start_line = start_line + 1
        content = "\n".join(lines[start_line - 1 : end_line])
        own_content = "\n".join(lines[body_start_line - 1 : own_end_line])
        sections.append(
            Section(
                level=level,
                heading=heading,
                normalized_heading=_normalize_heading(heading),
                start_line=start_line,
                end_line=end_line,
                body_start_line=body_start_line,
                content=content,
                own_content=own_content,
            )
        )
    return sections


def find_section(sections: list[Section], heading: str) -> Section:
    requested = heading.strip().casefold()
    normalized = _normalize_heading(heading)
    matches = [
        section
        for section in sections
        if section.heading.casefold() == requested
        or section.normalized_heading == normalized
    ]
    if not matches:
        raise CliError(4, "not_found", f"business knowledge heading not found: {heading}")
    if len(matches) > 1:
        candidates = ", ".join(section.heading for section in matches)
        raise CliError(4, "ambiguous", f"ambiguous heading; candidates: {candidates}")
    return matches[0]


def search_sections(
    sections: list[Section], query: str, limit: int
) -> list[dict[str, object]]:
    phrase = query.strip().casefold()
    if not phrase:
        raise CliError(2, "usage", "search query must not be empty")
    terms = phrase.split()
    ranked: list[tuple[int, int, dict[str, object]]] = []
    for section in sections:
        heading = section.heading.casefold()
        body = section.own_content.casefold()
        haystack = f"{heading}\n{body}"
        if not all(term in haystack for term in terms):
            continue
        score = 0
        if phrase in heading:
            score += 100
        score += sum(20 * heading.count(term) for term in terms)
        if phrase in body:
            score += 5
        score += sum(body.count(term) for term in terms)
        snippet = section.own_content.strip()
        if len(snippet) > 500:
            snippet = snippet[:497].rstrip() + "..."
        ranked.append(
            (
                -score,
                section.start_line,
                {
                    "heading": section.heading,
                    "start_line": section.start_line,
                    "end_line": section.end_line,
                    "snippet": snippet,
                    "score": score,
                },
            )
        )
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked[:limit]]


def _default_cache_root() -> Path:
    if os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"])
    elif os.environ.get("XDG_CACHE_HOME"):
        base = Path(os.environ["XDG_CACHE_HOME"])
    else:
        base = Path.home() / ".cache"
    return base / "Codex" / "knowledge-cache" / "generate-openapi-from-prd"


def _write_json(stream: TextIO, payload: dict[str, object]) -> None:
    stream.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")


class _CliArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliError(2, "usage", message)


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", required=True)
    parser.add_argument("--document", required=True)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--offline", action="store_true")


def _citation_url(
    source: SourceConfig,
    document: DocumentConfig,
    commit: str,
    start_line: int,
    end_line: int,
) -> str:
    repository_url = source.remote[:-4] if source.remote.endswith(".git") else source.remote
    return (
        f"{repository_url}/-/blob/{commit}/{document.path}"
        f"#L{start_line}-{end_line}"
    )


def _main_impl(
    argv: Sequence[str] | None = None,
    *,
    manifest_path: Path = MANIFEST_PATH,
    cache_root: Path | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = _CliArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(
        dest="command", required=True, parser_class=_CliArgumentParser
    )
    status_parser = subparsers.add_parser("status")
    _add_common_arguments(status_parser)
    sections_parser = subparsers.add_parser("sections")
    _add_common_arguments(sections_parser)
    search_parser = subparsers.add_parser("search")
    _add_common_arguments(search_parser)
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--limit", type=int, default=5)
    get_parser = subparsers.add_parser("get")
    _add_common_arguments(get_parser)
    get_parser.add_argument("--heading", required=True)
    get_parser.add_argument("--max-chars", type=int, default=8000)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.refresh and args.offline:
        raise CliError(2, "usage", "--refresh and --offline are mutually exclusive")
    if hasattr(args, "limit") and args.limit <= 0:
        raise CliError(2, "usage", "--limit must be greater than zero")
    if hasattr(args, "max_chars") and args.max_chars <= 0:
        raise CliError(2, "usage", "--max-chars must be greater than zero")

    source, document = load_source(manifest_path, args.source, args.document)
    cache = GitCache(source, cache_root or _default_cache_root())
    snapshot = cache.resolve(refresh=args.refresh, offline=args.offline)
    result: dict[str, object] = {"kind": "status"}
    if args.command == "sections":
        text = cache.read_document(snapshot, document)
        items = [
            {
                "level": section.level,
                "heading": section.heading,
                "normalized_heading": section.normalized_heading,
                "start_line": section.start_line,
                "end_line": section.end_line,
                "citation_url": _citation_url(
                    source,
                    document,
                    snapshot.commit,
                    section.start_line,
                    section.end_line,
                ),
            }
            for section in parse_sections(text)
        ]
        result = {"kind": "sections", "items": items}
    elif args.command == "search":
        text = cache.read_document(snapshot, document)
        matches = search_sections(parse_sections(text), args.query, args.limit)
        items = []
        for match in matches:
            item = dict(match)
            item["citation_url"] = _citation_url(
                source,
                document,
                snapshot.commit,
                int(match["start_line"]),
                int(match["end_line"]),
            )
            items.append(item)
        result = {"kind": "search", "query": args.query, "items": items}
    elif args.command == "get":
        text = cache.read_document(snapshot, document)
        section = find_section(parse_sections(text), args.heading)
        if len(section.content) > args.max_chars:
            raise CliError(
                2,
                "usage",
                "section exceeds --max-chars; choose a narrower heading or raise the limit",
            )
        result = {
            "kind": "section",
            "heading": section.heading,
            "normalized_heading": section.normalized_heading,
            "start_line": section.start_line,
            "end_line": section.end_line,
            "content": section.content,
            "citation_url": _citation_url(
                source,
                document,
                snapshot.commit,
                section.start_line,
                section.end_line,
            ),
        }

    payload: dict[str, object] = {
        "schema_version": 1,
        "ok": True,
        "source": {
            "id": source.id,
            "ref": source.ref,
            "commit": snapshot.commit,
            "commit_time": snapshot.commit_time,
            "freshness": snapshot.freshness,
            "cache_age_seconds": snapshot.cache_age_seconds,
        },
        "document": {
            "id": document.id,
            "path": document.path,
            "authority": document.authority,
        },
        "result": result,
        "warnings": list(snapshot.warnings),
    }
    _write_json(stdout, payload)
    return 0


def _validate_remote(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CliError(2, "config", "source remote must be a non-empty URL")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https", "file"}:
        raise CliError(2, "config", "source remote must use http, https, or file")
    if parsed.username is not None or parsed.password is not None:
        raise CliError(2, "config", "source remote must not contain credentials")
    return value


def _validate_ref(value: object) -> str:
    safe_ref = isinstance(value, str) and re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._/-]*", value
    )
    if not safe_ref or ".." in value or "//" in value or value.endswith(("/", ".", ".lock")):
        raise CliError(2, "config", "source ref is invalid")
    return value


def _validate_identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", value):
        raise CliError(
            2,
            "config",
            "business knowledge identifiers must use lowercase letters, digits, and hyphens",
        )
    return value


def load_source(
    manifest_path: Path, source_id: str, document_id: str
) -> tuple[SourceConfig, DocumentConfig]:
    _validate_identifier(source_id)
    _validate_identifier(document_id)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CliError(2, "config", "business knowledge manifest is unreadable") from exc
    if not isinstance(data, dict):
        raise CliError(2, "config", "business knowledge manifest must be a JSON object")
    if data.get("schema_version") != 1:
        raise CliError(2, "config", "unsupported manifest schema_version")
    try:
        source_data = data["sources"][source_id]
    except (KeyError, TypeError) as exc:
        raise CliError(2, "config", f"unknown business knowledge source: {source_id}") from exc
    if not isinstance(source_data, dict):
        raise CliError(2, "config", "business knowledge source must be a JSON object")
    documents_data = source_data.get("documents")
    if not isinstance(documents_data, dict) or not documents_data:
        raise CliError(2, "config", "business knowledge source must define documents")
    documents: dict[str, DocumentConfig] = {}
    for item_id, item_data in documents_data.items():
        if not isinstance(item_id, str):
            raise CliError(2, "config", "business knowledge document id must be text")
        _validate_identifier(item_id)
        if not isinstance(item_data, dict):
            raise CliError(2, "config", "business knowledge document must be a JSON object")
        try:
            path = _validate_document_path(item_data["path"])
            authority = item_data["authority"]
        except KeyError as exc:
            raise CliError(
                2, "config", "business knowledge document is missing required fields"
            ) from exc
        if authority != "background":
            raise CliError(2, "config", "document authority must be background")
        documents[item_id] = DocumentConfig(
            id=item_id,
            path=path,
            authority=authority,
        )
    source = SourceConfig(
        id=source_id,
        remote=_validate_remote(source_data.get("remote")),
        ref=_validate_ref(source_data.get("ref")),
        documents=documents,
    )
    try:
        document = documents[document_id]
    except KeyError as exc:
        raise CliError(
            2,
            "config",
            f"unknown business knowledge document for {source_id}: {document_id}",
        ) from exc
    return source, document


def main(
    argv: Sequence[str] | None = None,
    *,
    manifest_path: Path = MANIFEST_PATH,
    cache_root: Path | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    try:
        return _main_impl(
            argv,
            manifest_path=manifest_path,
            cache_root=cache_root,
            stdout=stdout,
            stderr=stderr,
        )
    except CliError as exc:
        _write_json(
            stderr,
            {
                "schema_version": 1,
                "ok": False,
                "error": {
                    "category": exc.category,
                    "message": exc.message,
                },
            },
        )
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
