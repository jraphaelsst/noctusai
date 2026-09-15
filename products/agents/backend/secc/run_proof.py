#!/usr/bin/env python3
"""run_proof.py — the SEC-C real-image isolation proof (roadmap
``julia-agents-academia-2026-09``, row SEC-C).

Builds the REAL agents ``runtime`` image (plus the proof-only
``secc-proof`` stage) and asserts the isolation properties
``bin/entrypoint.sh`` / ``bin/julia-cli-exec`` /
``products/agents/docker-compose.yml``'s security block claim, against a
container started EXACTLY the way prod will start it — the docker-run
flags are DERIVED from the compose file (``secc.compose_flags``), never
hand-copied.

Usage::

    python3 products/agents/backend/secc/run_proof.py [--tag TAG] [--keep]

Exits 0 iff every check passes; prints a table + JSON summary either way.

WHY A STANDALONE SCRIPT, NOT PYTEST: most of what this proves (docker
build, container start, capability inspection over SSH^Wdocker-exec) is
not unit-test-shaped — it's the real-image CI job itself, gated by the CI
workflow that runs it (``.github/workflows/test.yml``'s ``agents-secc-ci``
job), not by pytest collection. The one genuinely pure-logic slice
(compose→docker-run-flags) IS unit-tested, in
``tests/secc/test_compose_flags.py``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from secc.compose_flags import (  # noqa: E402
    GATE_NAMES,
    derive_security_flags,
    expected_capbnd_mask,
)

REPO_ROOT = _BACKEND_DIR.parents[2]
COMPOSE_PATH = REPO_ROOT / "products/agents/docker-compose.yml"
DOCKERFILE = REPO_ROOT / "products/agents/backend/Dockerfile"
ENTRYPOINT_SH = REPO_ROOT / "products/agents/backend/bin/entrypoint.sh"
WRAPPER_SH = REPO_ROOT / "products/agents/backend/bin/julia-cli-exec"
DRIVER_SCRIPT = _BACKEND_DIR / "secc" / "uvicorn_credentials_driver.py"
BUILD_AND_PUSH_SH = REPO_ROOT / "scripts/infra/build-and-push.sh"
BUILD_AND_PUSH_WORKFLOW = REPO_ROOT / ".github/workflows/build-and-push.yml"

_WRAPPER_PATH_IN_IMAGE = "/app/bin/julia-cli-exec"
_ENTRYPOINT_PATH_IN_IMAGE = "/app/bin/entrypoint.sh"
_BUNDLED_CLI_PATH_IN_IMAGE = "/usr/local/bin/claude-bundled"

# Non-secret placeholders only — this repo is PUBLIC (no client/company/
# knowledge content in any fixture, per CLAUDE.md). Mirrors the D1 manual
# proof's "degraded start with placeholder Supabase credentials, as
# designed" (roadmap, 2026-09-14). Deliberately NOT setting APP_ENV or any
# PRODUCT_URL_* — `is_deploy_context()` (seed/lib/backend/noctusai_lib/
# config/deploy_config.py) stays False, so the two `required_prod_config`
# keys (APPROVAL_ASSERTION_SECRETS, SOCIAL_WIRING_API_TOKEN) stay
# optional and boot never hard-aborts on them.
PLACEHOLDER_ENV = {
    "SUPABASE_URL": "https://secc-proof.invalid.supabase.co",
    "SUPABASE_ANON_KEY": "secc-proof-placeholder-anon-key",
    "SUPABASE_SERVICE_ROLE_KEY": "secc-proof-placeholder-service-role-key",
    "JWT_SECRET": "secc-proof-placeholder-jwt-secret-not-a-real-secret",
    "CORS_ORIGINS": "http://localhost:5173",
    "ANTHROPIC_API_KEY": "",
    "ACADEMIA_API_TOKEN": "secc-proof-placeholder-token",
    "JULIA_AGENT_ID": "00000000-0000-0000-0000-000000000000",
    "SOCIAL_WIRING_API_TOKEN": "secc-proof-placeholder-token",
    "APPROVAL_ASSERTION_SECRETS": "secc-proof-placeholder-secret",
}


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    data: dict = field(default_factory=dict)


def _run(cmd: list[str], *, timeout: int = 60, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input_text,
        cwd=str(REPO_ROOT),
    )


def _docker_run_flags_to_args(flags: list[str]) -> list[str]:
    return list(flags)


class Proof:
    def __init__(self, tag: str, keep: bool) -> None:
        self.tag = tag
        self.keep = keep
        self.results: list[CheckResult] = []
        self.runtime_image = f"noctus-agents-secc:{tag}-runtime"
        self.proof_image = f"noctus-agents-secc:{tag}-secc-proof"
        self.main_container = f"secc-proof-main-{tag}"
        self.runtime_container = f"secc-proof-runtime-{tag}"
        self._started_containers: list[str] = []

    def record(self, name: str, passed: bool, detail: str = "", data: dict | None = None) -> bool:
        self.results.append(CheckResult(name, passed, detail, data or {}))
        marker = "PASS" if passed else "FAIL"
        print(f"[{marker}] {name}" + (f" — {detail}" if detail else ""), flush=True)
        return passed

    # ── build ────────────────────────────────────────────────────────
    def build_images(self) -> bool:
        ok = True
        for target, image in (
            ("runtime", self.runtime_image),
            ("secc-proof", self.proof_image),
        ):
            proc = _run(
                [
                    "docker", "build",
                    "-f", str(DOCKERFILE),
                    "--target", target,
                    "-t", image,
                    str(REPO_ROOT),
                ],
                timeout=900,
            )
            passed = proc.returncode == 0
            ok = self.record(
                f"build_{target.replace('-', '_')}_image", passed,
                detail="" if passed else proc.stdout[-2000:] + proc.stderr[-2000:],
            ) and ok
        return ok

    # ── static / build-scope checks ─────────────────────────────────
    def check_build_and_push_never_builds_secc_proof(self) -> bool:
        text = BUILD_AND_PUSH_SH.read_text() if BUILD_AND_PUSH_SH.exists() else ""
        workflow_text = BUILD_AND_PUSH_WORKFLOW.read_text() if BUILD_AND_PUSH_WORKFLOW.exists() else ""
        combined = text + workflow_text
        mentions_secc_proof = "secc-proof" in combined
        return self.record(
            "build_and_push_never_builds_secc_proof",
            not mentions_secc_proof,
            detail=(
                "scripts/infra/build-and-push.sh + build-and-push.yml never "
                "reference the 'secc-proof' target"
                if not mentions_secc_proof
                else "FOUND a 'secc-proof' reference in the build/push path — "
                "this stage must never be tagged/pushed/deployed"
            ),
        )

    def check_wrapper_entrypoint_byte_identical(self) -> bool:
        ok = True
        for path_in_image, label in (
            (_WRAPPER_PATH_IN_IMAGE, "wrapper"),
            (_ENTRYPOINT_PATH_IN_IMAGE, "entrypoint"),
        ):
            digests = {}
            for image, tgt in ((self.runtime_image, "runtime"), (self.proof_image, "secc-proof")):
                proc = _run(
                    ["docker", "run", "--rm", "--entrypoint", "sha256sum", image, path_in_image],
                    timeout=30,
                )
                digests[tgt] = proc.stdout.split()[0] if proc.returncode == 0 and proc.stdout else None
            same = digests["runtime"] is not None and digests["runtime"] == digests["secc-proof"]
            ok = self.record(
                f"{label}_byte_identical_runtime_vs_secc_proof",
                same,
                detail=f"runtime={digests['runtime']} secc-proof={digests['secc-proof']}",
            ) and ok
        return ok

    # ── fail-closed entrypoint ──────────────────────────────────────
    def check_fail_closed(self, gate: str) -> bool:
        flags = derive_security_flags(COMPOSE_PATH, "agents", omit_gates=frozenset({gate}))
        name = f"secc-failclosed-{gate}-{uuid.uuid4().hex[:8]}"
        cmd = ["docker", "run", "--rm", "--name", name]
        for k, v in PLACEHOLDER_ENV.items():
            cmd += ["-e", f"{k}={v}"]
        cmd += _docker_run_flags_to_args(flags)
        cmd += [self.proof_image]
        try:
            proc = _run(cmd, timeout=20)
        except subprocess.TimeoutExpired:
            _run(["docker", "kill", name], timeout=10)
            return self.record(
                f"fail_closed_without_{gate}", False,
                detail="container did NOT fail closed within 20s (kept running) — real defect",
            )
        refused = proc.returncode != 0 and "entrypoint: refusing to start" in proc.stderr
        return self.record(
            f"fail_closed_without_{gate}", refused,
            detail=f"exit={proc.returncode} stderr={proc.stderr.strip()[-300:]}",
        )

    # ── the main long-lived proof container ─────────────────────────
    def start_main_container(self) -> bool:
        flags = derive_security_flags(COMPOSE_PATH, "agents")
        cmd = ["docker", "run", "-d", "--name", self.main_container, "-P"]
        for k, v in PLACEHOLDER_ENV.items():
            cmd += ["-e", f"{k}={v}"]
        cmd += _docker_run_flags_to_args(flags)
        cmd += [self.proof_image]
        proc = _run(cmd, timeout=30)
        if proc.returncode != 0:
            return self.record("start_main_container", False, detail=proc.stderr)
        self._started_containers.append(self.main_container)
        return self.record("start_main_container", True)

    def _published_port(self) -> int | None:
        proc = _run(["docker", "port", self.main_container, "8016/tcp"], timeout=10)
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        # "0.0.0.0:XXXXX" (possibly multiple lines for ipv4+ipv6)
        m = re.search(r":(\d+)$", proc.stdout.strip().splitlines()[0])
        return int(m.group(1)) if m else None

    def check_health(self) -> bool:
        port = self._published_port()
        if port is None:
            return self.record("health_endpoint_200", False, detail="no published port found")
        deadline = time.time() + 45
        last_detail = ""
        while time.time() < deadline:
            proc = _run(
                ["curl", "-fsS", "-o", "/dev/null", "-w", "%{http_code}", f"http://127.0.0.1:{port}/api/health"],
                timeout=10,
            )
            last_detail = f"curl_rc={proc.returncode} code={proc.stdout.strip()}"
            if proc.returncode == 0 and proc.stdout.strip() == "200":
                return self.record("health_endpoint_200", True, detail=last_detail)
            time.sleep(2)
        return self.record("health_endpoint_200", False, detail=last_detail)

    def check_uvicorn_identity(self) -> bool:
        # No `procps` in the slim runtime image (no `pgrep`) — scan
        # `/proc/*/cmdline` directly, same technique `secc/probe.py` uses
        # from the OTHER side of this same isolation boundary. Match
        # `app.main:app` (the real uvicorn invocation from
        # `bin/entrypoint.sh`), NOT the substring `uvicorn` — this whole
        # script's own text is itself part of the invoking shell's
        # cmdline, so grepping for `uvicorn` classically matches ITSELF
        # (the "ps aux | grep pattern matches grep" gotcha) and reports
        # root's own uid for the "target".
        find_pid_script = (
            "for p in /proc/[0-9]*; do "
            "  if tr '\\0' ' ' < \"$p/cmdline\" 2>/dev/null | grep -q 'app[.]main:app'; then "
            "    echo \"${p#/proc/}\"; break; "
            "  fi; "
            "done"
        )
        proc = _run(
            ["docker", "exec", self.main_container, "sh", "-c",
             f"pid=$({find_pid_script}); cat /proc/$pid/status"],
            timeout=15,
        )
        if proc.returncode != 0 or not proc.stdout:
            return self.record("uvicorn_process_identity", False, detail=proc.stderr or "no /proc/<pid>/status output")
        status = _parse_proc_status(proc.stdout)
        expected_bnd = expected_capbnd_mask(COMPOSE_PATH, "agents")
        uid_fields = status.get("Uid", "").split()
        gid_fields = status.get("Gid", "").split()
        ok = (
            len(uid_fields) == 4 and all(f == "1000" for f in uid_fields)
            and len(gid_fields) == 4 and all(f == "1000" for f in gid_fields)
            and status.get("CapPrm") == expected_bnd
            and status.get("CapEff") == expected_bnd
            and status.get("CapAmb") == expected_bnd
            and status.get("NoNewPrivs") == "1"
        )
        self.record(
            "cap_inh_finding", True,
            detail=(
                f"CapInh={status.get('CapInh')!r} alongside CapAmb={status.get('CapAmb')!r} "
                "— informational, not a pass/fail gate (see report)."
            ),
            data={"CapInh": status.get("CapInh")},
        )
        return self.record(
            "uvicorn_process_identity", ok,
            detail=f"Uid={status.get('Uid')} Gid={status.get('Gid')} "
                   f"CapPrm={status.get('CapPrm')} CapEff={status.get('CapEff')} "
                   f"CapAmb={status.get('CapAmb')} NoNewPrivs={status.get('NoNewPrivs')} "
                   f"(expected CapBnd mask={expected_bnd})",
            data=status,
        )

    def _entrypoint_setpriv_prefix(self) -> str:
        """Extract the setpriv flag block ``bin/entrypoint.sh`` uses to drop
        from root to ``noctus`` (uid 1000) — DERIVED, never hand-copied, so
        a future entrypoint edit is caught here instead of silently
        leaving this harness's own reproduction stale."""
        text = ENTRYPOINT_SH.read_text()
        match = re.search(
            r"exec /usr/bin/setpriv \\\n(?P<flags>.*?)-- \\\n\s*uvicorn",
            text,
            re.DOTALL,
        )
        if not match:
            raise RuntimeError(
                "could not extract the setpriv invocation from bin/entrypoint.sh — "
                "the entrypoint's shape changed; update this regex deliberately."
            )
        flags = " ".join(match.group("flags").replace("\\", " ").split())
        return f"/usr/bin/setpriv {flags} --"

    def check_real_code_path_and_kill_reap(self) -> bool:
        setpriv_prefix = self._entrypoint_setpriv_prefix()
        driver_source = DRIVER_SCRIPT.read_text()
        cmd = [
            "docker", "exec", "-i", self.main_container,
            "sh", "-c", f"{setpriv_prefix} python3 -",
        ]
        try:
            proc = _run(cmd, timeout=150, input_text=driver_source)
        except subprocess.TimeoutExpired:
            return self.record("real_code_path_and_kill_reap", False, detail="driver script timed out")
        if proc.returncode != 0:
            return self.record(
                "real_code_path_and_kill_reap", False,
                detail=f"driver exited {proc.returncode}: {proc.stderr[-1500:]}",
            )
        result = None
        for line in proc.stdout.splitlines():
            if line.startswith("SECC_DRIVER_JSON:"):
                result = json.loads(line[len("SECC_DRIVER_JSON:"):])
                break
        if result is None:
            return self.record(
                "real_code_path_and_kill_reap", False,
                detail=f"driver produced no SECC_DRIVER_JSON line; stderr={proc.stderr[-1000:]}",
            )

        overall = True
        overall = self._check_spawn_diag("real_code_path_main_spawn", result["main_spawn"], expect_env_allowlist=True) and overall
        overall = self._check_spawn_diag("real_code_path_version_spawn", result["version_spawn"], expect_env_allowlist=True) and overall

        main_diag = (result["main_spawn"] or {}).get("diag") or {}
        overall = self._check_access_battery(main_diag.get("access_checks") or {}) and overall

        for i, kr in enumerate(result["kill_and_reap"]):
            passed = kr["alive_before_term"] and kr["survived_sigterm"] and kr["gone_after_kill"] and kr["proc_entry_removed"]
            overall = self.record(
                f"kill_and_reap_iteration_{i}", passed,
                detail=f"pid={kr['pid']} survived_sigterm={kr['survived_sigterm']} "
                       f"gone_after_kill={kr['gone_after_kill']} proc_entry_removed={kr['proc_entry_removed']}",
            ) and overall
        return overall

    def _check_spawn_diag(self, name: str, spawn: dict, *, expect_env_allowlist: bool) -> bool:
        diag = (spawn or {}).get("diag")
        if not diag:
            return self.record(name, False, detail=f"no probe diag captured (stderr={(spawn or {}).get('stderr', '')[-500:]})")
        allowlist = {
            "HOME", "TMPDIR", "PATH", "ANTHROPIC_API_KEY", "CLAUDE_CODE_ENTRYPOINT",
            "CLAUDE_AGENT_SDK_VERSION", "DISABLE_AUTOUPDATER",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
            # `LC_CTYPE` — a CPython interpreter artefact, not a wrapper leak:
            # the REAL bundled CLI is a native binary with no libc locale
            # startup step; `secc/probe.py` (the proof-only CLI stand-in) IS
            # a python3 script, and glibc's locale init sets this in the
            # child's own apparent environment on exactly this base image
            # (verified live, 2026-09-15) even though the wrapper's
            # `env -i` never passed it. Documented by exact name per the
            # task brief; never present for the real CLI.
            "LC_CTYPE",
        }
        env_keys = set(diag.get("env_keys") or [])
        extra_env = env_keys - allowlist
        status = diag.get("proc_status") or {}
        ok = (
            diag.get("uid") == 1001
            and diag.get("gid") == 1001
            and diag.get("groups") == []
            and status.get("CapInh") == "0000000000000000"
            and status.get("CapPrm") == "0000000000000000"
            and status.get("CapEff") == "0000000000000000"
            and status.get("CapAmb") == "0000000000000000"
            and status.get("NoNewPrivs") == "1"
            and not extra_env
        )
        return self.record(
            name, ok,
            detail=f"uid={diag.get('uid')} gid={diag.get('gid')} groups={diag.get('groups')} "
                   f"caps={ {k: v for k, v in status.items() if k.startswith('Cap')} } "
                   f"NoNewPrivs={status.get('NoNewPrivs')} extra_env={sorted(extra_env)}",
            data=diag,
        )

    def _check_access_battery(self, access: dict) -> bool:
        overall = True
        expectations = {
            "proc_environ": "denied",
            "proc_mem": "denied",
            "proc_fd": "denied",
            "proc_cwd": "denied",
            "kill_minus_0": "denied",
            "tmp_read": "denied",
            "setpriv_reuid_1000": "denied",
        }
        for key, expected in expectations.items():
            entry = access.get(key)
            passed = bool(entry) and entry.get("outcome") == expected
            overall = self.record(
                f"as_uid_1001_{key}", passed,
                detail=json.dumps(entry) if entry else "missing",
            ) and overall
        writable = access.get("writable_paths")
        writable_ok = isinstance(writable, list) and writable == ["/run/julia"]
        overall = self.record(
            "as_uid_1001_writable_paths_only_run_julia", writable_ok,
            detail=f"writable_paths={writable}",
        ) and overall
        return overall

    # ── image contents ───────────────────────────────────────────────
    def check_image_contents(self) -> bool:
        overall = True
        proc = _run(
            ["docker", "run", "--rm", "--entrypoint", "find", self.runtime_image,
             "/", "-xdev", "-perm", "/6000", "-type", "f"],
            timeout=30,
        )
        setuid_files = [l for l in proc.stdout.splitlines() if l.strip()]
        overall = self.record(
            "image_no_setuid_setgid_files", not setuid_files,
            detail=f"found={setuid_files}" if setuid_files else "",
        ) and overall

        # `%a` on a SYMLINK itself is always 777 on Linux (the kernel
        # ignores a symlink's own mode bits for permission checks) —
        # `/usr/local/bin/claude-bundled` in the real `runtime` image IS a
        # symlink (the Dockerfile's `ln -s "$CLAUDE_BUNDLED" ...`). The
        # substantive properties for a symlink are: (a) its RESOLVED
        # target is root:root and not group/other-writable, and (b) the
        # containing directory can't be group/other-written (which would
        # let a non-root actor replace the symlink itself). Ask the shell
        # to resolve + report both, rather than hand-writing per-type
        # branches over three separate `docker run` calls.
        # `%F` (e.g. "symbolic link", "regular file") CONTAINS a space —
        # `|` as the field delimiter, never a bare space, so splitting
        # can't misparse "symbolic link" into two fields.
        script = (
            "for p in " + " ".join([_WRAPPER_PATH_IN_IMAGE, _ENTRYPOINT_PATH_IN_IMAGE, _BUNDLED_CLI_PATH_IN_IMAGE]) + "; do "
            "  stat -c '%U:%G|%a|%F|%n' \"$p\"; "
            "  if [ -L \"$p\" ]; then "
            "    real=$(readlink -f \"$p\"); "
            "    stat -c '%U:%G|%a|%F|%n' \"$real\"; "
            "    stat -c '%U:%G|%a|%F|%n' \"$(dirname \"$p\")\"; "
            "  fi; "
            "done"
        )
        proc = _run(
            ["docker", "run", "--rm", "--entrypoint", "sh", self.runtime_image, "-c", script],
            timeout=30,
        )
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        contents_ok = proc.returncode == 0 and len(lines) > 0
        for line in lines:
            owner_group, mode, ftype, _path = line.split("|", 3)
            if owner_group != "root:root":
                contents_ok = False
            is_symlink = ftype.strip() == "symbolic link"
            if is_symlink:
                continue  # its own mode bits are meaningless — the target/dir lines (below it) are what matter
            try:
                mode_int = int(mode, 8)
            except ValueError:
                contents_ok = False
                continue
            if mode_int & 0o022:  # group/other write bit
                contents_ok = False
        overall = self.record(
            "image_wrapper_entrypoint_bundled_root_owned_not_writable", contents_ok,
            detail="; ".join(lines),
        ) and overall
        return overall

    def check_bundled_cli_readonly_rootfs(self) -> bool:
        flags = derive_security_flags(COMPOSE_PATH, "agents")
        name = f"secc-runtime-cli-check-{uuid.uuid4().hex[:8]}"
        cmd = ["docker", "run", "--rm", "--name", name]
        for k, v in PLACEHOLDER_ENV.items():
            cmd += ["-e", f"{k}={v}"]
        cmd += _docker_run_flags_to_args(flags)
        cmd += ["--entrypoint", "sh", self.runtime_image, "-c", f"{_BUNDLED_CLI_PATH_IN_IMAGE} -v"]
        try:
            proc = _run(cmd, timeout=20)
        except subprocess.TimeoutExpired:
            _run(["docker", "kill", name], timeout=10)
            return self.record("bundled_cli_dash_v_on_readonly_rootfs", False, detail="timed out")
        ok = proc.returncode == 0 and proc.stdout.strip() != ""
        return self.record(
            "bundled_cli_dash_v_on_readonly_rootfs", ok,
            detail=f"exit={proc.returncode} stdout={proc.stdout.strip()[:200]} stderr={proc.stderr.strip()[:300]}",
        )

    # ── teardown ─────────────────────────────────────────────────────
    def teardown(self) -> None:
        if self.keep:
            print(f"--keep set: leaving {self._started_containers} running.")
            return
        for c in self._started_containers:
            _run(["docker", "rm", "-f", c], timeout=20)

    def run_all(self) -> bool:
        overall = True
        overall = self.build_images() and overall
        if not overall:
            return overall  # nothing else can proceed without images
        overall = self.check_build_and_push_never_builds_secc_proof() and overall
        overall = self.check_wrapper_entrypoint_byte_identical() and overall
        for gate in GATE_NAMES:
            overall = self.check_fail_closed(gate) and overall
        overall = self.check_image_contents() and overall
        overall = self.check_bundled_cli_readonly_rootfs() and overall
        try:
            if self.start_main_container():
                overall = self.check_health() and overall
                overall = self.check_uvicorn_identity() and overall
                overall = self.check_real_code_path_and_kill_reap() and overall
            else:
                overall = False
        finally:
            self.teardown()
        return overall


def _parse_proc_status(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=f"ci{int(time.time())}")
    parser.add_argument("--keep", action="store_true", help="leave the main proof container running (debugging)")
    parser.add_argument("--json-out", default=None, help="write the full results as JSON to this path")
    args = parser.parse_args()

    proof = Proof(tag=args.tag, keep=args.keep)
    ok = proof.run_all()

    print("\n=== SEC-C real-image isolation proof — summary ===")
    for r in proof.results:
        print(f"{'PASS' if r.passed else 'FAIL':4s}  {r.name}")
    print(f"\n{'ALL CHECKS PASSED' if ok else 'AT LEAST ONE CHECK FAILED'}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps([r.__dict__ for r in proof.results], indent=2, default=str)
        )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
