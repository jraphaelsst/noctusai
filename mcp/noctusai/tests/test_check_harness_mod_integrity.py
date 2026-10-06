"""`check_harness_mod_integrity` — a Claude Code mod is a UX layer over the
Python gates, never a gate. Both directions are pinned with fixture trees."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_harness_mod_integrity  # noqa: E402

GOOD_TS = '''
// $.process.run(["rm", "-rf"]) in a comment is ignored
export const h = async ($: any) => {
  const r = await $.process.run([py, "/x/mcp/noctusai/cli.py", "--harness-status"]);
  return r;
};
export const g = async ($: any) => { await foo().catch(() => ({ deny: "mod failed closed" })); };
'''


def _tree(tmp: Path, *, ts: str = GOOD_TS, test: bool = True, user_config: dict | None = None,
          version: str = "1.0.0", enabled: bool = True, listed: bool = True, extra_mod: bool = False) -> Path:
    mod = tmp / ".claude/mods/noc-harness"
    (mod / ".claude-plugin").mkdir(parents=True)
    (mod / "hooks").mkdir()
    pj = {"name": "noc-harness", "version": "1.0.0"}
    if user_config is not None:
        pj["userConfig"] = user_config
    (mod / ".claude-plugin/plugin.json").write_text(json.dumps(pj))
    (mod / "hooks/register.ts").write_text(ts)
    if test:
        (mod / "hooks/register.test.ts").write_text("// $.process.run(['bad'])\n")
    if extra_mod:
        (tmp / ".claude/mods/other").mkdir()
    (tmp / ".claude-plugin").mkdir()
    plugins = [{"name": "noc-harness", "source": "./.claude/mods/noc-harness", "version": version}] if listed else []
    (tmp / ".claude-plugin/marketplace.json").write_text(json.dumps({"name": "noctusai", "plugins": plugins}))
    (tmp / ".claude/settings.json").write_text(json.dumps({
        "extraKnownMarketplaces": {"noctusai": {"source": {"source": "directory", "path": "./"}}},
        "enabledPlugins": {"noc-harness@noctusai": enabled},
    }))
    return tmp


def _msgs(tmp: Path) -> str:
    return "\n".join(i["issue"] for i in check_harness_mod_integrity(repo_root=tmp))


class TestCheckHarnessModIntegrity:
    def test_vacuous_when_no_mods_no_marketplace(self, tmp_path):
        assert check_harness_mod_integrity(repo_root=tmp_path) == []

    def test_clean_tree_passes(self, tmp_path):
        assert check_harness_mod_integrity(repo_root=_tree(tmp_path)) == []

    def test_version_mismatch(self, tmp_path):
        assert "version" in _msgs(_tree(tmp_path, version="2.0.0"))

    def test_undecided_enable_state_flagged(self, tmp_path):
        assert "enabledPlugins" in _msgs(_tree(tmp_path, enabled=None))

    def test_explicitly_disabled_is_a_decision(self, tmp_path):
        # `false` is the rollback switch, not drift.
        assert check_harness_mod_integrity(repo_root=_tree(tmp_path, enabled=False)) == []

    def test_mod_folder_not_listed(self, tmp_path):
        assert "not listed" in _msgs(_tree(tmp_path, extra_mod=True))

    def test_marketplace_empty_lists_nothing(self, tmp_path):
        assert "not listed" in _msgs(_tree(tmp_path, listed=False))

    def test_mods_without_marketplace(self, tmp_path):
        t = _tree(tmp_path)
        (t / ".claude-plugin/marketplace.json").unlink()
        assert "marketplace.json" in _msgs(t)

    def test_foreign_spawn_flagged(self, tmp_path):
        ts = 'await $.process.run(["git", "status"]);'
        assert "cli.py --harness" in _msgs(_tree(tmp_path, ts=ts))

    def test_cli_without_harness_flag_flagged(self, tmp_path):
        ts = 'await $.process.spawn([py, "cli.py", "--check-foo"]);'
        assert "cli.py --harness" in _msgs(_tree(tmp_path, ts=ts))

    def test_non_literal_argv_flagged(self, tmp_path):
        assert "cli.py --harness" in _msgs(_tree(tmp_path, ts="await $.process.run(argv);"))

    def test_event_flag_allowed(self, tmp_path):
        ts = 'await $.process.run(["python3", "cli.py", "--harness-event", "{}"]);'
        assert check_harness_mod_integrity(repo_root=_tree(tmp_path, ts=ts)) == []

    def test_root_interpolated_cli_path_allowed(self, tmp_path):
        ts = 'await $.process.run(["python3", `${root}/mcp/noctusai/cli.py`, "--harness-status"], { cwd: root });'
        assert check_harness_mod_integrity(repo_root=_tree(tmp_path, ts=ts)) == []

    def test_interpolated_script_name_flagged(self, tmp_path):
        ts = 'await $.process.run(["python3", `${root}/${script}`, "--harness-status"]);'
        assert "cli.py --harness" in _msgs(_tree(tmp_path, ts=ts))

    def test_deny_outside_catch_flagged(self, tmp_path):
        ts = GOOD_TS + '\nexport const bad = () => ({ deny: "no" });'
        assert "deny" in _msgs(_tree(tmp_path, ts=ts))

    def test_missing_test_file(self, tmp_path):
        assert "no `*.test.ts`" in _msgs(_tree(tmp_path, test=False))

    def test_userconfig_gate_names_flagged(self, tmp_path):
        uc = {"disableGuard": {"title": "x"}, "banner": {"title": "Hook switch"}, "ok": {"title": "Show banner"}}
        msgs = _msgs(_tree(tmp_path, user_config=uc))
        assert "disableGuard" in msgs and "banner" in msgs and "`ok`" not in msgs

    def test_userconfig_ux_only_passes(self, tmp_path):
        uc = {"showBanner": {"title": "Show banner"}}
        assert check_harness_mod_integrity(repo_root=_tree(tmp_path, user_config=uc)) == []

    def test_live_repo_is_clean(self):
        assert check_harness_mod_integrity() == []
