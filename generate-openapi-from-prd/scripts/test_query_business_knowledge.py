import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("query_business_knowledge.py")


def load_cli_module():
    if not SCRIPT.exists():
        raise AssertionError("query_business_knowledge.py must provide the CLI behavior")
    spec = importlib.util.spec_from_file_location("query_business_knowledge", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("query_business_knowledge.py must be importable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_manifest(
    directory: Path,
    *,
    document_path: str,
    remote: str = "https://gitlab.example.test/ops/project-docs.git",
) -> Path:
    manifest = directory / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": {
                    "xinxintong": {
                        "remote": remote,
                        "ref": "master",
                        "documents": {
                            "product-overview": {
                                "path": document_path,
                                "authority": "background",
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest


def run_git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout.strip()


class LocalGitRepository:
    document_path = Path("products/xinxintong/product-overview.md")

    def __init__(self, root: Path) -> None:
        self.path = root / "remote"
        self.path.mkdir()
        run_git(self.path, "init", "-b", "master")
        run_git(self.path, "config", "user.email", "tests@example.test")
        run_git(self.path, "config", "user.name", "Business Knowledge Tests")

    def commit_document(self, content: str) -> str:
        target = self.path / self.document_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        run_git(self.path, "add", self.document_path.as_posix())
        run_git(self.path, "commit", "-m", "docs: update overview")
        return run_git(self.path, "rev-parse", "HEAD")


class ManifestTests(unittest.TestCase):
    def test_loads_allowlisted_source_and_document(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = write_manifest(
                Path(temp_dir),
                document_path="products/xinxintong/product-overview.md",
            )

            source, document = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )

        self.assertEqual(source.id, "xinxintong")
        self.assertEqual(source.ref, "master")
        self.assertEqual(document.path, "products/xinxintong/product-overview.md")
        self.assertEqual(document.authority, "background")

    def test_rejects_unsafe_document_paths(self) -> None:
        cli = load_cli_module()
        unsafe_paths = ("../secret.md", "/secret.md", "C:/secret.md", "notes.txt")
        for unsafe_path in unsafe_paths:
            with self.subTest(path=unsafe_path), tempfile.TemporaryDirectory() as temp_dir:
                manifest = write_manifest(Path(temp_dir), document_path=unsafe_path)
                with self.assertRaises(cli.CliError) as caught:
                    cli.load_source(manifest, "xinxintong", "product-overview")
                self.assertEqual(caught.exception.exit_code, 2)
                self.assertIn("safe relative Markdown path", caught.exception.message)

    def test_unknown_source_or_document_is_a_config_error(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = write_manifest(
                Path(temp_dir),
                document_path="products/xinxintong/product-overview.md",
            )
            for source_id, document_id in (
                ("unknown", "product-overview"),
                ("xinxintong", "unknown"),
            ):
                with self.subTest(source=source_id, document=document_id):
                    with self.assertRaises(cli.CliError) as caught:
                        cli.load_source(manifest, source_id, document_id)
                    self.assertEqual(caught.exception.exit_code, 2)
                    self.assertEqual(caught.exception.category, "config")

    def test_rejects_manifest_values_that_weaken_the_allowlist(self) -> None:
        cli = load_cli_module()
        cases = (
            ("schema_version", 2),
            ("remote", "https://user:secret@gitlab.example.test/project.git"),
            ("ref", "master\nbad"),
            ("authority", "requirements"),
        )
        for field, value in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp_dir:
                manifest = write_manifest(
                    Path(temp_dir),
                    document_path="products/xinxintong/product-overview.md",
                )
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if field == "schema_version":
                    data[field] = value
                elif field == "authority":
                    data["sources"]["xinxintong"]["documents"]["product-overview"][
                        field
                    ] = value
                else:
                    data["sources"]["xinxintong"][field] = value
                manifest.write_text(json.dumps(data), encoding="utf-8")

                with self.assertRaises(cli.CliError) as caught:
                    cli.load_source(manifest, "xinxintong", "product-overview")

                self.assertEqual(caught.exception.exit_code, 2)
                self.assertEqual(caught.exception.category, "config")

    def test_malformed_manifest_is_a_config_error(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "sources.json"
            manifest.write_text("{not-json", encoding="utf-8")

            with self.assertRaises(cli.CliError) as caught:
                cli.load_source(manifest, "xinxintong", "product-overview")

        self.assertEqual(caught.exception.exit_code, 2)
        self.assertEqual(caught.exception.category, "config")

    def test_incomplete_manifest_structure_is_a_controlled_config_error(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "sources": {"xinxintong": {}},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(cli.CliError) as caught:
                cli.load_source(manifest, "xinxintong", "product-overview")

        self.assertEqual(caught.exception.exit_code, 2)
        self.assertEqual(caught.exception.category, "config")

    def test_rejects_identifiers_that_could_escape_the_cache_directory(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = write_manifest(
                Path(temp_dir),
                document_path="products/xinxintong/product-overview.md",
            )
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["sources"]["../escape"] = data["sources"].pop("xinxintong")
            manifest.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaises(cli.CliError) as caught:
                cli.load_source(manifest, "../escape", "product-overview")

        self.assertEqual(caught.exception.exit_code, 2)
        self.assertEqual(caught.exception.category, "config")


class GitCacheTests(unittest.TestCase):
    def test_first_resolve_clones_and_reads_the_fixed_document(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            expected_commit = remote.commit_document("# 产品\n\n补贴计入个税。\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            source, document = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )

            cache = cli.GitCache(source, root / "cache")
            snapshot = cache.resolve(refresh=False, offline=False)
            content = cache.read_document(snapshot, document)

        self.assertEqual(snapshot.commit, expected_commit)
        self.assertEqual(snapshot.freshness, "fresh")
        self.assertEqual(content, "# 产品\n\n补贴计入个税。\n")

    def test_document_read_preserves_exact_utf8_text_and_line_offsets(self) -> None:
        cli = load_cli_module()
        expected = "\n# 产品\n\n补贴计入个税。\n\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            remote.commit_document(expected)
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            source, document = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )
            cache = cli.GitCache(source, root / "cache")
            snapshot = cache.resolve(refresh=False, offline=False)

            content = cache.read_document(snapshot, document)

        self.assertEqual(content, expected)

    def test_offline_without_cache_does_not_clone(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            remote.commit_document("# 产品\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            source, _ = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )
            cache = cli.GitCache(source, root / "cache")

            with self.assertRaises(cli.CliError) as caught:
                cache.resolve(refresh=False, offline=True)

            self.assertEqual(caught.exception.exit_code, 3)
            self.assertIn("offline", caught.exception.message)
            self.assertFalse(cache.repo_dir.exists())

    def test_offline_uses_cached_commit_without_changing_refresh_time(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            first_commit = remote.commit_document("# 产品\n\n旧内容。\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            source, document = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )
            cache = cli.GitCache(source, root / "cache")
            cache.resolve(refresh=False, offline=False)
            state = json.loads(cache.state_path.read_text(encoding="utf-8"))
            state["last_refresh_epoch"] = 1.0
            cache.state_path.write_text(json.dumps(state), encoding="utf-8")
            remote.commit_document("# 产品\n\n新内容。\n")

            snapshot = cache.resolve(refresh=False, offline=True)
            content = cache.read_document(snapshot, document)
            persisted = json.loads(cache.state_path.read_text(encoding="utf-8"))

        self.assertEqual(snapshot.commit, first_commit)
        self.assertEqual(snapshot.freshness, "stale")
        self.assertTrue(snapshot.warnings)
        self.assertEqual(persisted["last_refresh_epoch"], 1.0)
        self.assertEqual(content, "# 产品\n\n旧内容。\n")

    def test_forced_refresh_moves_to_the_new_remote_commit(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            remote.commit_document("# 产品\n\n第一版。\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            source, document = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )
            cache = cli.GitCache(source, root / "cache")
            cache.resolve(refresh=False, offline=False)
            expected_commit = remote.commit_document("# 产品\n\n第二版。\n")

            snapshot = cache.resolve(refresh=True, offline=False)
            content = cache.read_document(snapshot, document)

        self.assertEqual(snapshot.commit, expected_commit)
        self.assertEqual(snapshot.freshness, "fresh")
        self.assertEqual(content, "# 产品\n\n第二版。\n")

    def test_default_reuses_fresh_cache_without_changing_refresh_time(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            first_commit = remote.commit_document("# 产品\n\n第一版。\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            source, document = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )
            cache = cli.GitCache(source, root / "cache")
            cache.resolve(refresh=False, offline=False)
            before = json.loads(cache.state_path.read_text(encoding="utf-8"))
            remote.commit_document("# 产品\n\n第二版。\n")

            snapshot = cache.resolve(refresh=False, offline=False)
            content = cache.read_document(snapshot, document)
            after = json.loads(cache.state_path.read_text(encoding="utf-8"))

        self.assertEqual(snapshot.commit, first_commit)
        self.assertEqual(content, "# 产品\n\n第一版。\n")
        self.assertEqual(after["last_refresh_epoch"], before["last_refresh_epoch"])

    def test_default_refreshes_cache_after_the_ttl(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            remote.commit_document("# 产品\n\n第一版。\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            source, document = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )
            cache = cli.GitCache(source, root / "cache")
            cache.resolve(refresh=False, offline=False)
            state = json.loads(cache.state_path.read_text(encoding="utf-8"))
            state["last_refresh_epoch"] = 1.0
            cache.state_path.write_text(json.dumps(state), encoding="utf-8")
            expected_commit = remote.commit_document("# 产品\n\n第二版。\n")

            snapshot = cache.resolve(refresh=False, offline=False)
            content = cache.read_document(snapshot, document)

        self.assertEqual(snapshot.commit, expected_commit)
        self.assertEqual(snapshot.freshness, "fresh")
        self.assertEqual(content, "# 产品\n\n第二版。\n")

    def test_default_refresh_failure_returns_marked_stale_cache(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            expected_commit = remote.commit_document("# 产品\n\n缓存内容。\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            source, document = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )
            cache = cli.GitCache(source, root / "cache")
            cache.resolve(refresh=False, offline=False)
            state = json.loads(cache.state_path.read_text(encoding="utf-8"))
            state["last_refresh_epoch"] = 1.0
            cache.state_path.write_text(json.dumps(state), encoding="utf-8")
            remote.path.rename(root / "remote-unavailable")

            snapshot = cache.resolve(refresh=False, offline=False)
            content = cache.read_document(snapshot, document)

        self.assertEqual(snapshot.commit, expected_commit)
        self.assertEqual(snapshot.freshness, "stale")
        self.assertTrue(snapshot.warnings)
        self.assertEqual(content, "# 产品\n\n缓存内容。\n")

    def test_forced_refresh_failure_does_not_fall_back(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            remote.commit_document("# 产品\n\n缓存内容。\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            source, _ = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )
            cache = cli.GitCache(source, root / "cache")
            cache.resolve(refresh=False, offline=False)
            remote.path.rename(root / "remote-unavailable")

            with self.assertRaises(cli.CliError) as caught:
                cache.resolve(refresh=True, offline=False)

        self.assertEqual(caught.exception.exit_code, 3)
        self.assertEqual(caught.exception.category, "network")

    def test_update_lock_blocks_a_second_cache_writer(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            remote.commit_document("# 产品\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            source, _ = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )
            cache = cli.GitCache(
                source, root / "cache", lock_timeout_seconds=0.05
            )
            cache.source_dir.mkdir(parents=True)
            cache.lock_path.mkdir()

            with self.assertRaises(cli.CliError) as caught:
                cache.resolve(refresh=False, offline=False)

        self.assertEqual(caught.exception.exit_code, 5)
        self.assertEqual(caught.exception.category, "cache")
        self.assertIn("another process", caught.exception.message)

    def test_failed_initial_clone_does_not_publish_a_partial_repository(self) -> None:
        cli = load_cli_module()

        class PartialCloneFailureCache(cli.GitCache):
            def _git(self, *arguments: str, network: bool = False) -> str:
                if arguments and arguments[0] == "clone":
                    partial_target = Path(arguments[-1])
                    partial_target.mkdir(parents=True)
                    (partial_target / "partial").write_text("incomplete", encoding="utf-8")
                    raise cli.CliError(3, "network", "simulated clone failure")
                return super()._git(*arguments, network=network)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            remote.commit_document("# 产品\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            source, _ = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )
            cache = PartialCloneFailureCache(source, root / "cache")

            with self.assertRaises(cli.CliError):
                cache.resolve(refresh=False, offline=False)

            self.assertFalse(cache.repo_dir.exists())

    def test_failed_state_publish_preserves_the_previous_snapshot(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            first_commit = remote.commit_document("# 产品\n\n第一版。\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            source, _ = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )
            cache = cli.GitCache(source, root / "cache")
            cache.resolve(refresh=False, offline=False)
            remote.commit_document("# 产品\n\n第二版。\n")

            with mock.patch.object(cli.os, "replace", side_effect=OSError("simulated")):
                with self.assertRaises(cli.CliError) as caught:
                    cache.resolve(refresh=True, offline=False)

            persisted = json.loads(cache.state_path.read_text(encoding="utf-8"))

        self.assertEqual(caught.exception.exit_code, 5)
        self.assertEqual(persisted["commit"], first_commit)

    def test_rejects_a_corrupt_commit_in_cached_state(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            remote.commit_document("# 产品\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            source, _ = cli.load_source(
                manifest, "xinxintong", "product-overview"
            )
            cache = cli.GitCache(source, root / "cache")
            cache.resolve(refresh=False, offline=False)
            state = json.loads(cache.state_path.read_text(encoding="utf-8"))
            state["commit"] = "--help"
            cache.state_path.write_text(json.dumps(state), encoding="utf-8")

            with self.assertRaises(cli.CliError) as caught:
                cache.resolve(refresh=False, offline=True)

        self.assertEqual(caught.exception.exit_code, 5)
        self.assertEqual(caught.exception.category, "cache")


class MarkdownTests(unittest.TestCase):
    document = """# 信信通

## 六、核心业务流程

总览。

### 6.3 非全半月结算与发薪

补贴计入应付。

#### 公式

实发 = 应付 - 个税。

### 6.4 连续劳务

项目包。

## 七、非全计税现状

累计个税。
"""
    search_document = """# 信信通

## 1. 税务说明

补贴进入应付金额。

## 2. 非全计税

补贴计入累计个税基数。

## 3. 补贴处理

配置补贴字段。
"""

    def test_parse_sections_returns_nested_ranges_and_direct_content(self) -> None:
        cli = load_cli_module()

        sections = cli.parse_sections(self.document)

        self.assertEqual(
            [section.heading for section in sections],
            [
                "信信通",
                "六、核心业务流程",
                "6.3 非全半月结算与发薪",
                "公式",
                "6.4 连续劳务",
                "七、非全计税现状",
            ],
        )
        settlement = sections[2]
        self.assertEqual(settlement.normalized_heading, "非全半月结算与发薪")
        self.assertEqual((settlement.start_line, settlement.end_line), (7, 14))
        self.assertIn("#### 公式", settlement.content)
        self.assertEqual(settlement.own_content.strip(), "补贴计入应付。")
        overview = sections[1]
        self.assertEqual((overview.start_line, overview.end_line), (3, 18))
        self.assertEqual(overview.own_content.strip(), "总览。")

    def test_find_section_accepts_full_or_normalized_heading(self) -> None:
        cli = load_cli_module()
        sections = cli.parse_sections(self.document)

        by_full_heading = cli.find_section(sections, "6.3 非全半月结算与发薪")
        by_normalized_heading = cli.find_section(sections, "非全半月结算与发薪")

        self.assertEqual(by_full_heading.start_line, 7)
        self.assertEqual(by_normalized_heading.start_line, 7)

    def test_find_section_reports_ambiguous_normalized_headings(self) -> None:
        cli = load_cli_module()
        sections = cli.parse_sections("## 1. 状态\n\n旧。\n\n## 2. 状态\n\n新。\n")

        with self.assertRaises(cli.CliError) as caught:
            cli.find_section(sections, "状态")

        self.assertEqual(caught.exception.exit_code, 4)
        self.assertEqual(caught.exception.category, "ambiguous")
        self.assertIn("1. 状态", caught.exception.message)
        self.assertIn("2. 状态", caught.exception.message)

    def test_find_section_reports_a_missing_heading(self) -> None:
        cli = load_cli_module()
        sections = cli.parse_sections(self.document)

        with self.assertRaises(cli.CliError) as caught:
            cli.find_section(sections, "不存在的章节")

        self.assertEqual(caught.exception.exit_code, 4)
        self.assertEqual(caught.exception.category, "not_found")

    def test_search_requires_all_terms_and_ranks_title_hits_first(self) -> None:
        cli = load_cli_module()
        sections = cli.parse_sections(self.search_document)

        tax_results = cli.search_sections(sections, "补贴 个税", limit=5)
        title_results = cli.search_sections(sections, "补贴", limit=2)

        self.assertEqual([item["heading"] for item in tax_results], ["2. 非全计税"])
        self.assertEqual(title_results[0]["heading"], "3. 补贴处理")
        self.assertEqual(len(title_results), 2)
        self.assertIn("累计个税基数", tax_results[0]["snippet"])

    def test_search_rejects_an_empty_query(self) -> None:
        cli = load_cli_module()
        sections = cli.parse_sections(self.search_document)

        with self.assertRaises(cli.CliError) as caught:
            cli.search_sections(sections, "   ", limit=5)

        self.assertEqual(caught.exception.exit_code, 2)
        self.assertEqual(caught.exception.category, "usage")


class CliTests(unittest.TestCase):
    def test_status_returns_ascii_json_with_snapshot_provenance(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            expected_commit = remote.commit_document("# 产品\n\n补贴。\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = cli.main(
                [
                    "status",
                    "--source",
                    "xinxintong",
                    "--document",
                    "product-overview",
                    "--refresh",
                ],
                manifest_path=manifest,
                cache_root=root / "cache",
                stdout=stdout,
                stderr=stderr,
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(stdout.getvalue().isascii())
        self.assertEqual(stderr.getvalue(), "")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["source"]["commit"], expected_commit)
        self.assertEqual(
            payload["document"]["path"],
            "products/xinxintong/product-overview.md",
        )

    def test_sections_returns_heading_tree_with_fixed_commit_citations(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            expected_commit = remote.commit_document(
                "# 产品\n\n## 六、流程\n\n说明。\n\n### 6.1 结算\n\n补贴。\n"
            )
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            stdout = io.StringIO()

            exit_code = cli.main(
                [
                    "sections",
                    "--source",
                    "xinxintong",
                    "--document",
                    "product-overview",
                ],
                manifest_path=manifest,
                cache_root=root / "cache",
                stdout=stdout,
                stderr=io.StringIO(),
            )

        payload = json.loads(stdout.getvalue())
        items = payload["result"]["items"]
        self.assertEqual(exit_code, 0)
        self.assertEqual([item["heading"] for item in items], ["产品", "六、流程", "6.1 结算"])
        self.assertEqual(items[1]["level"], 2)
        self.assertIn(expected_commit, items[1]["citation_url"])
        self.assertTrue(stdout.getvalue().isascii())

    def test_search_returns_limited_snippets_with_citations(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            expected_commit = remote.commit_document(
                "# 产品\n\n## 七、非全计税现状\n\n补贴计入累计个税基数。\n\n"
                "## 八、其他\n\n补贴不在这里计算个税。\n"
            )
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            stdout = io.StringIO()

            exit_code = cli.main(
                [
                    "search",
                    "--source",
                    "xinxintong",
                    "--document",
                    "product-overview",
                    "--query",
                    "补贴 个税",
                    "--limit",
                    "1",
                ],
                manifest_path=manifest,
                cache_root=root / "cache",
                stdout=stdout,
                stderr=io.StringIO(),
            )

        payload = json.loads(stdout.getvalue())
        items = payload["result"]["items"]
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["heading"], "七、非全计税现状")
        self.assertIn("累计个税基数", items[0]["snippet"])
        self.assertIn(expected_commit, items[0]["citation_url"])

    def test_get_returns_one_exact_section_with_nested_content(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            expected_commit = remote.commit_document(
                "# 产品\n\n## 六、核心流程\n\n总览。\n\n### 6.1 结算\n\n补贴。\n\n"
                "## 七、其他\n\n不应返回。\n"
            )
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            stdout = io.StringIO()

            exit_code = cli.main(
                [
                    "get",
                    "--source",
                    "xinxintong",
                    "--document",
                    "product-overview",
                    "--heading",
                    "核心流程",
                    "--max-chars",
                    "1000",
                ],
                manifest_path=manifest,
                cache_root=root / "cache",
                stdout=stdout,
                stderr=io.StringIO(),
            )

        payload = json.loads(stdout.getvalue())
        result = payload["result"]
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["heading"], "六、核心流程")
        self.assertIn("### 6.1 结算", result["content"])
        self.assertNotIn("七、其他", result["content"])
        self.assertIn(expected_commit, result["citation_url"])
        self.assertTrue(stdout.getvalue().isascii())

    def test_config_errors_are_ascii_json_with_the_stable_exit_code(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = write_manifest(
                root,
                document_path="products/xinxintong/product-overview.md",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = cli.main(
                [
                    "status",
                    "--source",
                    "unknown",
                    "--document",
                    "product-overview",
                    "--offline",
                ],
                manifest_path=manifest,
                cache_root=root / "cache",
                stdout=stdout,
                stderr=stderr,
            )

        payload = json.loads(stderr.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(stderr.getvalue().isascii())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["category"], "config")

    def test_refresh_and_offline_are_mutually_exclusive_usage_errors(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = write_manifest(
                root,
                document_path="products/xinxintong/product-overview.md",
            )
            stderr = io.StringIO()

            exit_code = cli.main(
                [
                    "status",
                    "--source",
                    "xinxintong",
                    "--document",
                    "product-overview",
                    "--refresh",
                    "--offline",
                ],
                manifest_path=manifest,
                cache_root=root / "cache",
                stdout=io.StringIO(),
                stderr=stderr,
            )

        payload = json.loads(stderr.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["error"]["category"], "usage")

    def test_argument_errors_are_structured_json(self) -> None:
        cli = load_cli_module()
        stderr = io.StringIO()

        exit_code = cli.main(
            ["unknown-command"],
            stdout=io.StringIO(),
            stderr=stderr,
        )

        payload = json.loads(stderr.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["error"]["category"], "usage")
        self.assertTrue(stderr.getvalue().isascii())

    def test_get_rejects_a_section_larger_than_max_chars(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = LocalGitRepository(root)
            remote.commit_document("# 产品\n\n## 说明\n\n这段正文超过限制。\n")
            manifest = write_manifest(
                root,
                document_path=remote.document_path.as_posix(),
                remote=remote.path.as_uri(),
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = cli.main(
                [
                    "get",
                    "--source",
                    "xinxintong",
                    "--document",
                    "product-overview",
                    "--heading",
                    "说明",
                    "--max-chars",
                    "5",
                ],
                manifest_path=manifest,
                cache_root=root / "cache",
                stdout=stdout,
                stderr=stderr,
            )

        payload = json.loads(stderr.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(payload["error"]["category"], "usage")
        self.assertIn("max-chars", payload["error"]["message"])

    def test_search_rejects_a_nonpositive_limit_before_accessing_git(self) -> None:
        cli = load_cli_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = write_manifest(
                root,
                document_path="products/xinxintong/product-overview.md",
            )
            stderr = io.StringIO()

            exit_code = cli.main(
                [
                    "search",
                    "--source",
                    "xinxintong",
                    "--document",
                    "product-overview",
                    "--query",
                    "补贴",
                    "--limit",
                    "0",
                ],
                manifest_path=manifest,
                cache_root=root / "cache",
                stdout=io.StringIO(),
                stderr=stderr,
            )

        payload = json.loads(stderr.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["error"]["category"], "usage")
        self.assertIn("limit", payload["error"]["message"])

    def test_script_entrypoint_uses_main_exit_code_and_json_errors(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "unknown-command"],
            capture_output=True,
            text=True,
            encoding="ascii",
            errors="strict",
            check=False,
        )

        payload = json.loads(result.stderr)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(payload["error"]["category"], "usage")


if __name__ == "__main__":
    unittest.main()
