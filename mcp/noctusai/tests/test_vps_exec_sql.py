"""Tests for `noctus.vps.exec_sql` — the VPS schema-execution wrapper.

The tool wraps the working idiom (cat-tmp + docker-cp + docker-exec-psql +
cleanup) that survives where `ssh "docker exec ... psql <<EOF"` silently
fails. Tests inject a fake SSH runner so no real SSH/docker is required.

KB § PATTERNS/devops/containerization-operations.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools.noctus.dev import vps_exec_sql


class FakeSshRunner:
    """Records every call + returns scripted (rc, stdout, stderr) per step."""

    def __init__(self, scripted: list[tuple[int, str, str]]):
        self.calls: list[tuple[str, str]] = []  # (host, cmd)
        self.scripted = list(scripted)

    def __call__(self, host: str, cmd: str) -> tuple[int, str, str]:
        self.calls.append((host, cmd))
        if not self.scripted:
            return 0, "", ""
        return self.scripted.pop(0)


# ───────────────────────── validation ─────────────────────────


class TestExecSqlValidation:
    def test_empty_sql_rejected(self):
        result = vps_exec_sql.exec_sql(sql="", container="c", db="d")
        assert result["ok"] is False
        assert "sql cannot be empty" in result["error"]
        assert result["returncode"] == -1

    def test_whitespace_sql_rejected(self):
        result = vps_exec_sql.exec_sql(sql="   \n  ", container="c", db="d")
        assert result["ok"] is False
        assert "sql cannot be empty" in result["error"]

    def test_empty_container_rejected(self):
        result = vps_exec_sql.exec_sql(sql="SELECT 1;", container="", db="d")
        assert result["ok"] is False
        assert "container cannot be empty" in result["error"]

    def test_empty_db_rejected(self):
        result = vps_exec_sql.exec_sql(sql="SELECT 1;", container="c", db="")
        assert result["ok"] is False
        assert "db cannot be empty" in result["error"]


# ──────────────────────── happy path ──────────────────────────


class TestExecSqlHappyPath:
    def test_emits_4_step_sequence(self):
        runner = FakeSshRunner([
            (0, "", ""),         # write-tmp
            (0, "", ""),         # docker cp
            (0, "CREATE TABLE\n", ""),  # docker exec psql
            (0, "", ""),         # cleanup
        ])
        result = vps_exec_sql.exec_sql(
            sql="CREATE TABLE x (id INT);",
            container="noctus-cache-pg",
            db="noctus_cache",
            ssh_runner=runner,
        )
        assert result["ok"] is True
        assert result["returncode"] == 0
        assert result["container"] == "noctus-cache-pg"
        assert result["db"] == "noctus_cache"
        assert result["cleanup_ok"] is True
        assert result["step"] == "psql-exec"
        assert "CREATE TABLE" in result["stdout"]

        # 4 SSH calls: write + cp + exec + cleanup
        assert len(runner.calls) == 4

    def test_emits_correct_step_shapes(self):
        runner = FakeSshRunner([(0, "", "")] * 4)
        vps_exec_sql.exec_sql(
            sql="SELECT 1;",
            container="noctus-cache-pg",
            db="noctus_cache",
            ssh_runner=runner,
        )
        # Step 1: cat > /tmp/...sql heredoc
        assert "cat >" in runner.calls[0][1]
        assert "noctus-exec-sql-" in runner.calls[0][1]
        # Step 2: docker cp <tmp> <container>:<tmp>
        assert "docker cp" in runner.calls[1][1]
        assert "noctus-cache-pg" in runner.calls[1][1]
        # Step 3: docker exec <container> psql -U <user> -d <db> -f <tmp>
        assert "docker exec" in runner.calls[2][1]
        assert "psql -U" in runner.calls[2][1]
        assert "noctus_cache" in runner.calls[2][1]
        assert "-f" in runner.calls[2][1]
        # Step 4: cleanup
        assert "rm -f" in runner.calls[3][1]

    def test_user_defaults_to_db(self):
        """When user is None, the effective user equals the db name."""
        runner = FakeSshRunner([(0, "", "")] * 4)
        result = vps_exec_sql.exec_sql(
            sql="SELECT 1;", container="c", db="my_db", ssh_runner=runner,
        )
        assert result["user"] == "my_db"
        # The psql command should carry `-U my_db`.
        assert "psql -U my_db" in runner.calls[2][1]

    def test_explicit_user_override(self):
        runner = FakeSshRunner([(0, "", "")] * 4)
        result = vps_exec_sql.exec_sql(
            sql="SELECT 1;", container="c", db="my_db", user="admin",
            ssh_runner=runner,
        )
        assert result["user"] == "admin"
        assert "psql -U admin" in runner.calls[2][1]

    def test_custom_host(self):
        runner = FakeSshRunner([(0, "", "")] * 4)
        vps_exec_sql.exec_sql(
            sql="SELECT 1;", container="c", db="d",
            host="other-vps", ssh_runner=runner,
        )
        # Every call should target other-vps
        assert all(call[0] == "other-vps" for call in runner.calls)


# ──────────────────────── failure paths ───────────────────────


class TestExecSqlFailurePaths:
    def test_write_tmp_failure_short_circuits(self):
        runner = FakeSshRunner([
            (1, "", "permission denied"),  # write-tmp fails
        ])
        result = vps_exec_sql.exec_sql(
            sql="SELECT 1;", container="c", db="d", ssh_runner=runner,
        )
        assert result["ok"] is False
        assert result["returncode"] == 1
        assert result["step"] == "write-tmp-file"
        assert "permission denied" in result["error"]
        # Only 1 SSH call attempted
        assert len(runner.calls) == 1

    def test_docker_cp_failure_runs_cleanup(self):
        runner = FakeSshRunner([
            (0, "", ""),                   # write-tmp ok
            (1, "", "No such container"),  # docker cp fails
            (0, "", ""),                   # cleanup
        ])
        result = vps_exec_sql.exec_sql(
            sql="SELECT 1;", container="bogus", db="d", ssh_runner=runner,
        )
        assert result["ok"] is False
        assert result["step"] == "docker-cp"
        assert "No such container" in result["error"]
        # Cleanup MUST run (3 calls total)
        assert len(runner.calls) == 3
        assert "rm -f" in runner.calls[2][1]

    def test_psql_failure_surfaces_returncode_and_cleans_up(self):
        runner = FakeSshRunner([
            (0, "", ""),                                # write-tmp
            (0, "", ""),                                # docker cp
            (3, "", "ERROR: syntax error at or near"),  # psql fails
            (0, "", ""),                                # cleanup
        ])
        result = vps_exec_sql.exec_sql(
            sql="GARBAGE;", container="c", db="d", ssh_runner=runner,
        )
        assert result["ok"] is False
        assert result["returncode"] == 3
        assert result["step"] == "psql-exec"
        assert "syntax error" in result["stderr"]
        assert result["cleanup_ok"] is True
        # Cleanup ran (4 calls)
        assert len(runner.calls) == 4

    def test_cleanup_failure_does_not_flip_ok(self):
        """A failed cleanup is reported but does not invalidate a successful psql."""
        runner = FakeSshRunner([
            (0, "", ""),         # write-tmp
            (0, "", ""),         # docker cp
            (0, "OK\n", ""),     # psql ok
            (1, "", "rm failed: device or resource busy"),  # cleanup fails
        ])
        result = vps_exec_sql.exec_sql(
            sql="SELECT 1;", container="c", db="d", ssh_runner=runner,
        )
        assert result["ok"] is True  # psql succeeded
        assert result["returncode"] == 0
        assert result["cleanup_ok"] is False
        assert "rm failed" in result["cleanup_err"]


# ─────────────────────────── cleanup ──────────────────────────


class TestExecSqlCleanupToggle:
    def test_cleanup_false_skips_cleanup_step(self):
        runner = FakeSshRunner([(0, "", "")] * 3)
        result = vps_exec_sql.exec_sql(
            sql="SELECT 1;", container="c", db="d",
            cleanup=False, ssh_runner=runner,
        )
        assert result["ok"] is True
        # Only 3 calls (no cleanup)
        assert len(runner.calls) == 3
        # cleanup_ok defaults True when cleanup wasn't attempted
        assert result["cleanup_ok"] is True


# ─────────────────────── tmp filename uniqueness ──────────────


class TestExecSqlTmpFilename:
    def test_tmp_path_unique_per_call(self):
        runner1 = FakeSshRunner([(0, "", "")] * 4)
        runner2 = FakeSshRunner([(0, "", "")] * 4)
        r1 = vps_exec_sql.exec_sql(
            sql="SELECT 1;", container="c", db="d", ssh_runner=runner1,
        )
        r2 = vps_exec_sql.exec_sql(
            sql="SELECT 1;", container="c", db="d", ssh_runner=runner2,
        )
        # Both should have noctus-exec-sql- prefix but different UUIDs
        assert r1["tmp_path"] != r2["tmp_path"]
        assert "noctus-exec-sql-" in r1["tmp_path"]
        assert "noctus-exec-sql-" in r2["tmp_path"]

    def test_tmp_path_in_tmp_dir(self):
        runner = FakeSshRunner([(0, "", "")] * 4)
        r = vps_exec_sql.exec_sql(
            sql="SELECT 1;", container="c", db="d", ssh_runner=runner,
        )
        assert r["tmp_path"].startswith("/tmp/")
        assert r["tmp_path"].endswith(".sql")
