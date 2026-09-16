#!/usr/bin/env python3
"""run_proof.py — the SEC-C real-image isolation proof (roadmap
``julia-agents-academia-2026-09``, row SEC-C; extended contract §E.11 /
roadmap D2 to the per-conversation slot layout).

Builds the REAL agents ``runtime`` image (plus the proof-only
``secc-proof`` stage) and asserts the isolation properties
``bin/entrypoint.sh`` / ``bin/julia-cli-exec`` / ``bin/julia-cli-slot`` /
``products/agents/docker-compose.yml``'s security block claim, against a
container started EXACTLY the way prod will start it — the docker-run
flags are DERIVED from the compose file (``secc.compose_flags``), never
hand-copied.

Usage::

    python3 products/agents/backend/secc/run_proof.py [--tag TAG] [--keep]

Exits 0 iff every check passes; prints a table + JSON summary either way.

WHY A STANDALONE SCRIPT, NOT PYTEST: most of what this proves (docker
build, container start, capability inspection over docker-exec) is not
unit-test-shaped — it's the real-image CI job itself, gated by the CI
workflow that runs it (``.github/workflows/agents-secc-ci.yml``), not by
pytest collection. The one genuinely pure-logic slice
(compose→docker-run-flags) IS unit-tested, in
``tests/secc/test_compose_flags.py``.

CONTRACT §E.11 "SEC-C harness additions" — the nine numbered checks this
module implements (``check1_*`` .. ``check9_*`` below, each recording one
or more independently-reported ``CheckResult`` rows):
  1. image: slot users/groups in the fixed range, no uid 1001,
     ``CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK=1``.
  2. mounts: per-slot tmpfs + handoff, derived from compose; fail-closed
     on a missing/wrong-owner/wrong-mode mount.
  3. wrapper refusals: exit 126, no probe output, for uid 1000 / an
     out-of-range uid / a mismatched ``CLAUDE_CONFIG_DIR``.
  4. two concurrent slots: EACCES/EPERM battery, no persona sentinel in
     any cmdline, all cap sets 0, groups only its own, a writable scan
     finds only its own slot.
  5. handoff: a sentinel transcript lands in slot 0's copy, unreadable
     from slot 1.
  6. SIGKILL leftovers cleaned by the release scan.
  7. a ``setsid`` grandchild orphan killed by the release scan.
  8. quota: slot 0 hits ENOSPC, slot 1 still writes.
  9. pool: the real ``SlotPool`` discovers 3 slots, refuses a 4th, and
     reserves again after a release.
"""
from __future__ import annotations

import argparse
import json
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
    handoff_tmpfs_spec,
    mutate_tmpfs_flag,
    normalize_octal_mode,
    normalize_size_to_kib,
    slot_tmpfs_specs,
)

REPO_ROOT = _BACKEND_DIR.parents[2]
COMPOSE_PATH = REPO_ROOT / "products/agents/docker-compose.yml"
DOCKERFILE = REPO_ROOT / "products/agents/backend/Dockerfile"
ENTRYPOINT_SH = REPO_ROOT / "products/agents/backend/bin/entrypoint.sh"
WRAPPER_SH = REPO_ROOT / "products/agents/backend/bin/julia-cli-exec"
SLOT_SCRIPT_SH = REPO_ROOT / "products/agents/backend/bin/julia-cli-slot"
DRIVER_SCRIPT = _BACKEND_DIR / "secc" / "uvicorn_credentials_driver.py"
POOL_DRIVER_SCRIPT = _BACKEND_DIR / "secc" / "slot_pool_driver.py"
HANDOFF_DRIVER_SCRIPT = _BACKEND_DIR / "secc" / "handoff_check_driver.py"
BUILD_AND_PUSH_SH = REPO_ROOT / "scripts/infra/build-and-push.sh"
BUILD_AND_PUSH_WORKFLOW = REPO_ROOT / ".github/workflows/build-and-push.yml"

_WRAPPER_PATH_IN_IMAGE = "/app/bin/julia-cli-exec"
_ENTRYPOINT_PATH_IN_IMAGE = "/app/bin/entrypoint.sh"
_SLOT_SCRIPT_PATH_IN_IMAGE = "/app/bin/julia-cli-slot"
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


def _mount_opts(mounts_text: str, mount: str) -> str | None:
    """The fs_mntops (4th ``/proc/mounts`` field) for the FIRST mount whose
    mount point EXACTLY matches ``mount`` — the same shape
    ``bin/entrypoint.sh``'s own ``_mount_opts`` awk one-liner reads."""
    for line in mounts_text.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[1] == mount:
            return fields[3]
    return None


def _opts_has_token(opts: str, token: str) -> bool:
    """Same substring idiom ``bin/entrypoint.sh``'s own ``_opts_has`` uses:
    wrapping both sides in commas turns "is this token present" into one
    substring test regardless of position."""
    return f",{token}," in f",{opts},"


class Proof:
    def __init__(self, tag: str, keep: bool) -> None:
        self.tag = tag
        self.keep = keep
        self.results: list[CheckResult] = []
        self.runtime_image = f"noctus-agents-secc:{tag}-runtime"
        self.proof_image = f"noctus-agents-secc:{tag}-secc-proof"
        self.main_container = f"secc-proof-main-{tag}"
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

    def check_wrapper_entrypoint_slot_byte_identical(self) -> bool:
        """Extends the original wrapper/entrypoint byte-identity proof to
        ``bin/julia-cli-slot`` too (contract §E.11 / roadmap D1's own
        Dockerfile comment: "extending the sha256 proof to cover it too is
        roadmap D2's row, not yet done here" — done here)."""
        ok = True
        for path_in_image, label in (
            (_WRAPPER_PATH_IN_IMAGE, "wrapper"),
            (_ENTRYPOINT_PATH_IN_IMAGE, "entrypoint"),
            (_SLOT_SCRIPT_PATH_IN_IMAGE, "slot_script"),
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

    # ── fail-closed entrypoint (whole-gate omission) ─────────────────
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

    # ── §E.11 D2 check 1: image slot users/groups/env ────────────────
    def check1_image_slot_users_and_env(self) -> bool:
        overall = True
        specs = slot_tmpfs_specs(COMPOSE_PATH, "agents")
        expected_users = {f"julia-cli-{s['index']}" for s in specs}
        expected_uids = {int(s["uid"]) for s in specs}

        proc = _run(
            ["docker", "run", "--rm", "--entrypoint", "sh", self.runtime_image, "-c", "cat /etc/passwd"],
            timeout=20,
        )
        passwd_ok = proc.returncode == 0
        found_users: dict[str, int] = {}
        found_gids: dict[str, int] = {}
        uid_1001_present = False
        for line in proc.stdout.splitlines():
            parts = line.split(":")
            if len(parts) < 4:
                continue
            name, uid_str, gid_str = parts[0], parts[2], parts[3]
            if not uid_str.isdigit():
                continue
            uid = int(uid_str)
            if uid == 1001:
                uid_1001_present = True
            if name in expected_users:
                found_users[name] = uid
                if gid_str.isdigit():
                    found_gids[name] = int(gid_str)
        users_ok = passwd_ok and found_users == {u: 2000 + int(u.rsplit("-", 1)[1]) for u in expected_users}
        overall = self.record(
            "e11_check1_slot_users_uids_in_fixed_range", users_ok,
            detail=f"expected={sorted(expected_uids)} found={found_users}",
        ) and overall
        overall = self.record(
            "e11_check1_no_uid_1001_in_image", passwd_ok and not uid_1001_present,
            detail="uid 1001 present in /etc/passwd" if uid_1001_present else "uid 1001 absent",
        ) and overall

        # Contract §E.11 image section, verbatim: "Slot users `julia-cli-K`
        # with uid AND gid `2000+K`." `useradd --user-group` creates a
        # matching-NAME group but does NOT pin its gid to the uid — on
        # this base image it auto-allocates from the system gid range
        # instead (observed: 999/998/997, not 2000/2001/2002). This is a
        # REAL DEFECT if it reproduces (see this project's delivery note)
        # — the check is left to fail honestly, never weakened to match
        # whatever gid the image happens to carry.
        expected_gids = {u: 2000 + int(u.rsplit("-", 1)[1]) for u in expected_users}
        gids_ok = passwd_ok and found_gids == expected_gids
        overall = self.record(
            "e11_check1_slot_group_gid_equals_uid", gids_ok,
            detail=f"expected={expected_gids} found={found_gids} "
                   "(contract §E.11: 'uid and gid 2000+K' — a mismatch here means "
                   "useradd --user-group did not pin the group's gid to the uid)",
        ) and overall

        proc = _run(
            ["docker", "run", "--rm", "--entrypoint", "id", self.runtime_image, "noctus"],
            timeout=20,
        )
        id_ok = proc.returncode == 0
        groups_in_output = set(re.findall(r"\d+\((julia-cli-\d+)\)", proc.stdout))
        groups_exactly_slots = id_ok and groups_in_output == expected_users
        overall = self.record(
            "e11_check1_noctus_groups_exactly_slot_groups", groups_exactly_slots,
            detail=f"id noctus -> {proc.stdout.strip()!r} groups={groups_in_output} expected={expected_users}",
        ) and overall

        proc = _run(
            ["docker", "run", "--rm", "--entrypoint", "sh", self.runtime_image, "-c",
             "printenv CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"],
            timeout=20,
        )
        skip_check_ok = proc.returncode == 0 and proc.stdout.strip() == "1"
        overall = self.record(
            "e11_check1_skip_version_check_env_set", skip_check_ok,
            detail=f"CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK={proc.stdout.strip()!r}",
        ) and overall
        return overall

    # ── §E.11 D2 check 2: mounts ──────────────────────────────────────
    def check2_mounts_match_compose(self) -> bool:
        proc = _run(["docker", "exec", self.main_container, "cat", "/proc/mounts"], timeout=10)
        if proc.returncode != 0:
            return self.record("e11_check2_mounts_readable", False, detail=proc.stderr)
        mounts_text = proc.stdout
        overall = True
        for spec in slot_tmpfs_specs(COMPOSE_PATH, "agents"):
            opts = _mount_opts(mounts_text, spec["mount"])
            sub_ok = (
                opts is not None
                and _opts_has_token(opts, f"uid={spec['uid']}")
                and _opts_has_token(opts, f"gid={spec['gid']}")
                and _opts_has_token(opts, f"mode={normalize_octal_mode(spec['mode'])}")
                and _opts_has_token(opts, f"size={normalize_size_to_kib(spec['size'])}")
            )
            overall = self.record(
                f"e11_check2_mount_matches_compose_{spec['mount']}", sub_ok,
                detail=f"expected uid={spec['uid']} gid={spec['gid']} "
                       f"mode={normalize_octal_mode(spec['mode'])} "
                       f"size={normalize_size_to_kib(spec['size'])}; got opts={opts}",
            ) and overall
        handoff = handoff_tmpfs_spec(COMPOSE_PATH, "agents")
        opts = _mount_opts(mounts_text, handoff["mount"])
        sub_ok = (
            opts is not None
            and _opts_has_token(opts, f"uid={handoff['uid']}")
            and _opts_has_token(opts, f"gid={handoff['gid']}")
            and _opts_has_token(opts, f"mode={normalize_octal_mode(handoff['mode'])}")
        )
        overall = self.record(
            f"e11_check2_mount_matches_compose_{handoff['mount']}", sub_ok,
            detail=f"expected uid={handoff['uid']} gid={handoff['gid']} "
                   f"mode={normalize_octal_mode(handoff['mode'])}; got opts={opts}",
        ) and overall
        return overall

    def _run_with_mutated_flags(self, label: str, flags: list[str]) -> bool:
        name = f"secc-failclosed-mount-{label}-{uuid.uuid4().hex[:8]}"
        cmd = ["docker", "run", "--rm", "--name", name]
        for k, v in PLACEHOLDER_ENV.items():
            cmd += ["-e", f"{k}={v}"]
        cmd += flags
        cmd += [self.proof_image]
        try:
            proc = _run(cmd, timeout=20)
        except subprocess.TimeoutExpired:
            _run(["docker", "kill", name], timeout=10)
            return self.record(
                f"e11_check2_failclosed_{label}", False,
                detail="container did NOT fail closed within 20s — real defect",
            )
        refused = proc.returncode != 0 and "entrypoint: refusing to start" in proc.stderr
        return self.record(
            f"e11_check2_failclosed_{label}", refused,
            detail=f"exit={proc.returncode} stderr={proc.stderr.strip()[-300:]}",
        )

    def check2_mount_fail_closed_variants(self) -> bool:
        overall = True
        flags = derive_security_flags(COMPOSE_PATH, "agents")
        slot0 = next(s for s in slot_tmpfs_specs(COMPOSE_PATH, "agents") if s["index"] == "0")

        missing = mutate_tmpfs_flag(flags, "/run/julia-0", None)
        overall = self._run_with_mutated_flags("missing_slot_mount", missing) and overall

        wrong_owner_entry = re.sub(
            rf"uid={slot0['uid']},gid={slot0['gid']}", "uid=9999,gid=9999", slot0["raw"]
        )
        wrong_owner = mutate_tmpfs_flag(flags, "/run/julia-0", wrong_owner_entry)
        overall = self._run_with_mutated_flags("wrong_owner", wrong_owner) and overall

        wrong_mode_entry = re.sub(rf"mode={slot0['mode']}", "mode=0755", slot0["raw"])
        wrong_mode = mutate_tmpfs_flag(flags, "/run/julia-0", wrong_mode_entry)
        overall = self._run_with_mutated_flags("wrong_mode", wrong_mode) and overall
        return overall

    # ── §E.11 D2 check 3: wrapper refusals ────────────────────────────
    def check3_wrapper_refusals(self) -> bool:
        overall = True

        def _exec_as(uid: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
            cmd = ["docker", "exec", "--user", uid]
            for k, v in (extra_env or {}).items():
                cmd += ["-e", f"{k}={v}"]
            cmd += [self.main_container, _WRAPPER_PATH_IN_IMAGE]
            return _run(cmd, timeout=15)

        proc = _exec_as("1000")
        ok = proc.returncode == 126 and proc.stdout.strip() == "" and "outside the slot range" in proc.stderr
        overall = self.record(
            "e11_check3_wrapper_refuses_uid_1000", ok,
            detail=f"exit={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr.strip()[-200:]}",
        ) and overall

        proc = _exec_as("9999")
        ok = proc.returncode == 126 and proc.stdout.strip() == "" and "outside the slot range" in proc.stderr
        overall = self.record(
            "e11_check3_wrapper_refuses_uid_out_of_range", ok,
            detail=f"exit={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr.strip()[-200:]}",
        ) and overall

        proc = _exec_as("2000", {"CLAUDE_CONFIG_DIR": "/run/julia-1/home/.claude"})
        ok = proc.returncode == 126 and proc.stdout.strip() == "" and "does not match the expected" in proc.stderr
        overall = self.record(
            "e11_check3_wrapper_refuses_mismatched_config_dir", ok,
            detail=f"exit={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr.strip()[-200:]}",
        ) and overall
        return overall

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

    # ── §E.11 D2 checks 3(cont)/4/6(part)/8: the multi-slot driver ────
    def run_slot_driver(self) -> dict | None:
        setpriv_prefix = self._entrypoint_setpriv_prefix()
        sentinel = "SECC-PERSONA-SENTINEL-" + uuid.uuid4().hex
        append_path_in_image = "/run/julia-handoff/0/append.md"

        # Seed as `noctus` (uid 1000) — it OWNS the shared handoff mount
        # (compose: uid=1000,gid=1000), so no elevated capability is
        # needed for any of this. Root uid 0 CANNOT do this in this
        # container (cap_drop: ALL strips CAP_DAC_OVERRIDE too — verified
        # live: `docker exec --user 0 ... mkdir /run/julia-handoff/0`
        # itself gets EACCES) — a real, if orthogonal, illustration of
        # I4's "root isn't privileged here either" intent. Only an EMPTY
        # handoff directory + the (unrelated) append.md persona file are
        # seeded here — the "durable transcripts" *.jsonl handoff file
        # itself is `run_handoff_check_driver`'s job, run LATER, so its
        # own copy-step side effects never contaminate these clean
        # identity/caps/env spawns (see that method + this project's
        # delivery note for the real D1 defect this split exists to
        # isolate).
        setup = _run(
            [
                "docker", "exec", "--user", "noctus", self.main_container, "sh", "-c",
                f"mkdir -p /run/julia-handoff/0 && chmod 0750 /run/julia-handoff/0 "
                f"&& chgrp julia-cli-0 /run/julia-handoff/0 "
                f"&& printf 'persona: %s' '{sentinel}' > {append_path_in_image} "
                f"&& chmod 0640 {append_path_in_image} && chgrp julia-cli-0 {append_path_in_image}",
            ],
            timeout=15,
        )
        if setup.returncode != 0:
            self.record("e11_driver_setup_seeds_handoff_dir", False, detail=setup.stderr)
            return None
        self.record("e11_driver_setup_seeds_handoff_dir", True)

        driver_source = (
            DRIVER_SCRIPT.read_text()
            .replace("__SECC_APPEND_PATH__", append_path_in_image)
            .replace("__SECC_SENTINEL__", sentinel)
        )
        cmd = [
            "docker", "exec", "-i", self.main_container,
            "sh", "-c", f"{setpriv_prefix} python3 -",
        ]
        try:
            proc = _run(cmd, timeout=180, input_text=driver_source)
        except subprocess.TimeoutExpired:
            self.record("e11_driver_ran", False, detail="driver script timed out")
            return None
        if proc.returncode != 0:
            self.record(
                "e11_driver_ran", False,
                detail=f"driver exited {proc.returncode}: {proc.stderr[-2000:]}",
            )
            return None
        result = None
        for line in proc.stdout.splitlines():
            if line.startswith("SECC_DRIVER_JSON:"):
                result = json.loads(line[len("SECC_DRIVER_JSON:"):])
                break
        if result is None:
            self.record(
                "e11_driver_ran", False,
                detail=f"driver produced no SECC_DRIVER_JSON line; stderr={proc.stderr[-1000:]}",
            )
            return None
        self.record("e11_driver_ran", True)
        return result

    # ── §E.11 D2 check 5: the dedicated, LATER, handoff-file driver ───
    def run_handoff_check_driver(self) -> dict | None:
        sid = str(uuid.uuid4())
        handoff_file_in_image = f"/run/julia-handoff/0/{sid}.jsonl"
        sentinel_content = json.dumps({"type": "mirror-frame", "sid": sid}) + "\n"

        # Resolve the group's ACTUAL current gid via `getent` — NEVER a
        # hand-copied "2000" literal. This is deliberate: the contract
        # says "uid AND gid 2000+K" for the slot users, and if D1's image
        # ever satisfies that, this resolves to 2000 and the check below
        # passes; if it doesn't (as observed — see this project's
        # delivery note), this resolves to whatever the REAL gid is,
        # so the chgrp below succeeds (noctus IS a member of that real
        # group either way) and the SUBSEQUENT read-as-slot-0 check fails
        # for the RIGHT, attributable reason instead of a harness-side
        # "wrong literal" false negative.
        getent = _run(
            ["docker", "exec", "--user", "noctus", self.main_container, "getent", "group", "julia-cli-0"],
            timeout=10,
        )
        if getent.returncode != 0 or not getent.stdout.strip():
            self.record("e11_check5_resolve_slot0_group_gid", False, detail=getent.stderr)
            return None
        actual_gid = getent.stdout.strip().split(":")[2]
        self.record(
            "e11_check5_resolve_slot0_group_gid", True,
            detail=f"julia-cli-0 gid={actual_gid} (contract expects 2000; a mismatch here "
                   "is the real defect this project's delivery note reports)",
        )

        setup = _run(
            [
                "docker", "exec", "-i", "--user", "noctus", self.main_container, "sh", "-c",
                f"cat > {handoff_file_in_image} "
                f"&& chmod 0640 {handoff_file_in_image} && chgrp {actual_gid} {handoff_file_in_image}",
            ],
            timeout=15,
            input_text=sentinel_content,
        )
        if setup.returncode != 0:
            self.record("e11_driver_setup_seeds_handoff_file", False, detail=setup.stderr)
            return None
        self.record("e11_driver_setup_seeds_handoff_file", True)

        setpriv_prefix = self._entrypoint_setpriv_prefix()
        driver_source = (
            HANDOFF_DRIVER_SCRIPT.read_text()
            .replace("__SECC_SID__", sid)
            .replace("__SECC_HANDOFF_FILE__", handoff_file_in_image)
        )
        cmd = [
            "docker", "exec", "-i", self.main_container,
            "sh", "-c", f"{setpriv_prefix} python3 -",
        ]
        try:
            proc = _run(cmd, timeout=60, input_text=driver_source)
        except subprocess.TimeoutExpired:
            self.record("e11_handoff_driver_ran", False, detail="handoff driver script timed out")
            return None
        if proc.returncode != 0:
            self.record(
                "e11_handoff_driver_ran", False,
                detail=f"handoff driver exited {proc.returncode}: {proc.stderr[-2000:]}",
            )
            return None
        result = None
        for line in proc.stdout.splitlines():
            if line.startswith("SECC_HANDOFF_DRIVER_JSON:"):
                result = json.loads(line[len("SECC_HANDOFF_DRIVER_JSON:"):])
                break
        if result is None:
            self.record(
                "e11_handoff_driver_ran", False,
                detail=f"handoff driver produced no SECC_HANDOFF_DRIVER_JSON line; stderr={proc.stderr[-1000:]}",
            )
            return None
        self.record("e11_handoff_driver_ran", True)
        result["_sid"] = sid
        return result

    def _check_spawn_diag(self, name: str, spawn: dict, expected_uid: int) -> bool:
        diag = (spawn or {}).get("diag")
        if not diag:
            return self.record(name, False, detail=f"no probe diag captured (stderr={(spawn or {}).get('stderr', '')[-500:]})")
        allowlist = {
            # 9 keys (contract §E.11: "the wrapper's own env -i ships 8
            # keys... §E.11 adds CLAUDE_CONFIG_DIR, making 9") — NOT the
            # old §E.5 8-key allowlist; a stale 8-key copy here would
            # itself flag CLAUDE_CONFIG_DIR as an "extra_env" leak, which
            # is a harness bug, not a real one (caught + fixed in this
            # slice: the old single-slot design never carried it).
            "HOME", "TMPDIR", "CLAUDE_CONFIG_DIR", "PATH", "ANTHROPIC_API_KEY",
            "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_AGENT_SDK_VERSION", "DISABLE_AUTOUPDATER",
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
            diag.get("uid") == expected_uid
            and diag.get("gid") == expected_uid
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

    def _check_access_battery(self, name_prefix: str, access: dict, expected_writable: str) -> bool:
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
                f"{name_prefix}_{key}", passed,
                detail=json.dumps(entry) if entry else "missing",
            ) and overall
        writable = access.get("writable_paths")
        writable_ok = isinstance(writable, list) and writable == [expected_writable]
        overall = self.record(
            f"{name_prefix}_writable_paths_only_own_slot", writable_ok,
            detail=f"writable_paths={writable} expected=[{expected_writable}]",
        ) and overall
        return overall

    def check3_and_check4_from_driver(self, driver_result: dict) -> bool:
        overall = True

        # -- version-check spawn: SDK's un-`user=` shape, uid 1000, still
        #    refused by the wrapper's own range check even though
        #    CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK=1 means this spawn never
        #    actually happens any more (defence in depth). --------------
        vs = driver_result.get("version_spawn") or {}
        ok = vs.get("returncode") == 126 and vs.get("diag") is None and "outside the slot range" in (vs.get("stderr") or "")
        overall = self.record(
            "e11_check3_version_check_spawn_refused_as_noctus", ok,
            detail=f"returncode={vs.get('returncode')} stderr={(vs.get('stderr') or '')[-200:]}",
        ) and overall

        # -- check 4: main-turn identity/caps/env for slot 0 and slot 1,
        #    PLUS the reused "protect uvicorn from the CLI" battery (the
        #    original SEC-C intent, orthogonal to but still valid under
        #    §E.11) and the writable-scan-only-own-slot property. --------
        main_spawns = driver_result.get("main_spawns") or {}
        for k, uid in (("0", 2000), ("1", 2001)):
            spawn = main_spawns.get(k) or {}
            overall = self._check_spawn_diag(f"e11_check4_slot{k}_identity_caps_env", spawn, uid) and overall
            access = (spawn.get("diag") or {}).get("access_checks") or {}
            overall = self._check_access_battery(
                f"e11_check4_slot{k}_protects_uvicorn", access, f"/run/julia-{k}"
            ) and overall

        # -- check 4: cross-slot EACCES/EPERM battery (slot 1 -> slot 0) --
        cross = driver_result.get("cross_slot_probe") or {}
        cross_diag = cross.get("diag") or {}
        cross_checks = cross_diag.get("cross_slot_checks") or {}
        expectations = {
            "proc_environ": "denied",
            "proc_mem": "denied",
            "proc_fd": "denied",
            "proc_cwd": "denied",
            "kill_minus_0": "denied",
            "sigterm": "denied",
            "ptrace_attach": "denied",
            "target_slot_dir_listing": "denied",
            "target_handoff_dir_listing": "denied",
        }
        for key, expected in expectations.items():
            entry = cross_checks.get(key)
            passed = bool(entry) and entry.get("outcome") == expected
            overall = self.record(
                f"e11_check4_cross_slot_{key}", passed,
                detail=json.dumps(entry) if entry else f"missing (cross_checks={cross_checks!r})",
            ) and overall

        # -- check 4: persona sentinel never appears on any /proc/*/cmdline
        hits = driver_result.get("sentinel_scan_hits")
        overall = self.record(
            "e11_check4_no_persona_sentinel_in_any_cmdline",
            hits == [],
            detail=f"pids matching sentinel text in cmdline: {hits}",
        ) and overall

        return overall

    def check5_handoff_from_handoff_driver(self, handoff_result: dict) -> bool:
        """Contract §E.11 D2 check 5. Uses the DEDICATED
        ``secc/handoff_check_driver.py`` result (run separately, later —
        see ``run_handoff_check_driver``'s own docstring for why)."""
        overall = True
        sid = handoff_result.get("_sid")

        turn = handoff_result.get("handoff_turn") or {}
        readback = (handoff_result.get("read_back") or {}).get("diag") or {}
        copy_info = readback.get("handoff_copy") or {}
        copy_ok = (
            turn.get("returncode") == 0
            and bool(copy_info.get("copy_exists"))
            and sid in (copy_info.get("copy_content") or "")
        )
        overall = self.record(
            "e11_check5_handoff_copy_landed_in_slot0_projects_dir", copy_ok,
            detail=f"handoff_turn_returncode={turn.get('returncode')} "
                   f"handoff_turn_stderr={(turn.get('stderr') or '')[-300:]} "
                   f"copy_path={copy_info.get('copy_path')} copy_exists={copy_info.get('copy_exists')} "
                   f"content_has_sid={sid in (copy_info.get('copy_content') or '')}",
        ) and overall

        slot1_read = (handoff_result.get("slot1_source_read") or {}).get("diag") or {}
        entry = slot1_read.get("read_path_check")
        unreadable_ok = bool(entry) and entry.get("outcome") == "denied"
        overall = self.record(
            "e11_check5_handoff_source_unreadable_from_slot1", unreadable_ok,
            detail=json.dumps(entry) if entry else "missing",
        ) and overall
        return overall

    def check6_kill_and_reap_from_driver(self, driver_result: dict) -> bool:
        overall = True
        for i, kr in enumerate(driver_result.get("kill_and_reap") or []):
            passed = kr["alive_before_term"] and kr["survived_sigterm"] and kr["gone_after_kill"] and kr["proc_entry_removed"]
            overall = self.record(
                f"kill_and_reap_iteration_{i}", passed,
                detail=f"user={kr.get('user')} pid={kr['pid']} survived_sigterm={kr['survived_sigterm']} "
                       f"gone_after_kill={kr['gone_after_kill']} proc_entry_removed={kr['proc_entry_removed']}",
            ) and overall
        return overall

    def check8_quota_from_driver(self, driver_result: dict) -> bool:
        overall = True
        fill = (driver_result.get("quota_fill") or {}).get("diag") or {}
        quota = fill.get("quota") or {}
        got_enospc = bool(quota.get("got_enospc"))
        overall = self.record(
            "e11_check8_slot0_hits_enospc", got_enospc,
            detail=f"written_bytes={quota.get('written_bytes')} errno={quota.get('errno')} "
                   f"hit_safety_cap={quota.get('hit_safety_cap')}",
        ) and overall

        other = (driver_result.get("quota_other_write") or {}).get("diag") or {}
        write_test = other.get("write_test") or {}
        other_ok = bool(write_test.get("ok"))
        overall = self.record(
            "e11_check8_slot1_still_writes_after_slot0_enospc", other_ok,
            detail=json.dumps(write_test),
        ) and overall
        return overall

    # ── §E.11 D2 checks 6(rest)/7/9: the pool driver ──────────────────
    def run_pool_driver(self) -> dict | None:
        setpriv_prefix = self._entrypoint_setpriv_prefix()
        # SIGKILL leftovers (check 6) — seed junk into slot 0's tmpfs AS
        # SLOT 0's OWN uid (2000): a leftover regular file, a chmod-000
        # directory with a nested file, and a 10 MB file — the exact
        # shape contract §E.11 D2 check 6 lists. NOT root: root lacks
        # CAP_DAC_OVERRIDE in this container (cap_drop: ALL strips it
        # too — verified live, same finding as ``run_slot_driver``'s own
        # setup) and could not write into a 0700 dir it doesn't own
        # anyway; uid 2000 owns `/run/julia-0` outright, so no capability
        # is needed for any of this.
        seed = _run(
            [
                "docker", "exec", "--user", "2000", self.main_container, "sh", "-c",
                "set -e; "
                "mkdir -p /run/julia-0/locked; "
                "printf 'leftover from a SIGKILLed turn' > /run/julia-0/junk.txt; "
                "printf 'nested leftover' > /run/julia-0/locked/inside.txt; "
                "chmod 000 /run/julia-0/locked; "
                "dd if=/dev/zero of=/run/julia-0/big.bin bs=1M count=10 status=none",
            ],
            timeout=15,
        )
        if seed.returncode != 0:
            self.record("e11_check6_seed_leftovers", False, detail=seed.stderr)
            return None
        self.record("e11_check6_seed_leftovers", True)

        cmd = [
            "docker", "exec", "-i", self.main_container,
            "sh", "-c", f"{setpriv_prefix} python3 -",
        ]
        try:
            proc = _run(cmd, timeout=90, input_text=POOL_DRIVER_SCRIPT.read_text())
        except subprocess.TimeoutExpired:
            self.record("e11_pool_driver_ran", False, detail="pool driver timed out")
            return None
        if proc.returncode != 0:
            self.record(
                "e11_pool_driver_ran", False,
                detail=f"pool driver exited {proc.returncode}: {proc.stderr[-2000:]}",
            )
            return None
        result = None
        for line in proc.stdout.splitlines():
            if line.startswith("SECC_POOL_DRIVER_JSON:"):
                result = json.loads(line[len("SECC_POOL_DRIVER_JSON:"):])
                break
        if result is None:
            self.record(
                "e11_pool_driver_ran", False,
                detail=f"pool driver produced no SECC_POOL_DRIVER_JSON line; stderr={proc.stderr[-1000:]}",
            )
            return None
        self.record("e11_pool_driver_ran", True)
        return result

    def check6_sweep_from_pool_driver(self, pool_result: dict) -> bool:
        overall = True
        sweep = pool_result.get("sweep") or {}
        release_ok = sweep.get("release_raised") is None
        overall = self.record(
            "e11_check6_release_sweep_did_not_raise", release_ok,
            detail=f"release_raised={sweep.get('release_raised')} health_after={sweep.get('health_after_release')}",
        ) and overall

        # `--user 2000` (slot 0's own uid, which owns the mount) — root
        # cannot list a 0700 dir it doesn't own in this container either
        # (cap_drop: ALL strips CAP_DAC_OVERRIDE too), and this listing
        # only matters AFTER release, when it should be genuinely empty.
        proc = _run(
            ["docker", "exec", "--user", "2000", self.main_container, "sh", "-c",
             "ls -A /run/julia-0 2>&1; echo ---; df -B1 /run/julia-0 | tail -1"],
            timeout=10,
        )
        listing, _, df_line = proc.stdout.partition("---")
        listing = listing.strip()
        empty_ok = proc.returncode == 0 and listing == ""
        overall = self.record(
            "e11_check6_slot0_dir_empty_after_release", empty_ok,
            detail=f"ls -A output={listing!r}",
        ) and overall

        usage_ok = True
        used_bytes = None
        m = re.search(r"\S+\s+\d+\s+(\d+)\s+\d+", df_line.strip())
        if m:
            used_bytes = int(m.group(1))
            # "Near 0" — allow a small slack (a few KiB of tmpfs directory
            # metadata) rather than demanding a literal exact zero.
            usage_ok = used_bytes < 256 * 1024
        overall = self.record(
            "e11_check6_slot0_tmpfs_usage_near_zero_after_release", usage_ok,
            detail=f"used_bytes={used_bytes} df_line={df_line.strip()!r}",
        ) and overall
        return overall

    def check7_orphan_from_pool_driver(self, pool_result: dict) -> bool:
        orphan = pool_result.get("orphan") or {}
        if orphan.get("error"):
            return self.record("e11_check7_orphan_scenario_ran", False, detail=orphan["error"])
        overall = True
        overall = self.record(
            "e11_check7_orphan_alive_before_release",
            bool(orphan.get("orphan_alive_before_release")),
            detail=f"orphan_pid={orphan.get('orphan_pid')}",
        ) and overall
        overall = self.record(
            "e11_check7_orphan_gone_after_release",
            orphan.get("orphan_alive_after_release") is False
            and orphan.get("orphan_still_findable_after_release") is False,
            detail=f"alive_after={orphan.get('orphan_alive_after_release')} "
                   f"still_findable_after={orphan.get('orphan_still_findable_after_release')} "
                   f"release_raised={orphan.get('release_raised')}",
        ) and overall
        return overall

    def check9_pool_from_pool_driver(self, pool_result: dict) -> bool:
        overall = True
        discovery = pool_result.get("discovery") or {}
        overall = self.record(
            "e11_check9_pool_discovers_3_slots",
            discovery.get("reserved_indices") == [0, 1, 2],
            detail=f"reserved_indices={discovery.get('reserved_indices')}",
        ) and overall
        overall = self.record(
            "e11_check9_fourth_reservation_is_none",
            bool(discovery.get("fourth_reservation_is_none")),
            detail=f"fourth_reservation_is_none={discovery.get('fourth_reservation_is_none')}",
        ) and overall
        overall = self.record(
            "e11_check9_reserve_works_again_after_release",
            bool(discovery.get("fifth_reservation_succeeded")),
            detail=f"released_index={discovery.get('released_index')} "
                   f"fifth_reservation_index={discovery.get('fifth_reservation_index')}",
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

        script = (
            "for p in " + " ".join(
                [_WRAPPER_PATH_IN_IMAGE, _ENTRYPOINT_PATH_IN_IMAGE, _SLOT_SCRIPT_PATH_IN_IMAGE, _BUNDLED_CLI_PATH_IN_IMAGE]
            ) + "; do "
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
                continue
            try:
                mode_int = int(mode, 8)
            except ValueError:
                contents_ok = False
                continue
            if mode_int & 0o022:
                contents_ok = False
        overall = self.record(
            "image_wrapper_entrypoint_slot_bundled_root_owned_not_writable", contents_ok,
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
        overall = self.check_wrapper_entrypoint_slot_byte_identical() and overall
        overall = self.check1_image_slot_users_and_env() and overall
        for gate in GATE_NAMES:
            overall = self.check_fail_closed(gate) and overall
        overall = self.check2_mount_fail_closed_variants() and overall
        overall = self.check_image_contents() and overall
        overall = self.check_bundled_cli_readonly_rootfs() and overall
        try:
            if self.start_main_container():
                overall = self.check_health() and overall
                overall = self.check_uvicorn_identity() and overall
                overall = self.check2_mounts_match_compose() and overall
                overall = self.check3_wrapper_refusals() and overall

                driver_result = self.run_slot_driver()
                if driver_result is not None:
                    overall = self.check3_and_check4_from_driver(driver_result) and overall
                    overall = self.check6_kill_and_reap_from_driver(driver_result) and overall
                    overall = self.check8_quota_from_driver(driver_result) and overall
                else:
                    overall = False

                handoff_result = self.run_handoff_check_driver()
                if handoff_result is not None:
                    overall = self.check5_handoff_from_handoff_driver(handoff_result) and overall
                else:
                    overall = False

                pool_result = self.run_pool_driver()
                if pool_result is not None:
                    overall = self.check6_sweep_from_pool_driver(pool_result) and overall
                    overall = self.check7_orphan_from_pool_driver(pool_result) and overall
                    overall = self.check9_pool_from_pool_driver(pool_result) and overall
                else:
                    overall = False
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
