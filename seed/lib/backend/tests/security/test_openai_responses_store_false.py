"""Every OpenAI Responses API call in the seed must pass store=False.

The Responses API retains requests/outputs server-side by default (unlike
chat.completions). Owner order: no transcripts retained at the vendor.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "noctusai_lib"


def test_every_responses_create_or_parse_passes_store_false():
    offenders = []
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"create", "parse", "stream"}
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "responses"
            ):
                kw = {k.arg: k.value for k in node.keywords}
                v = kw.get("store")
                if not (isinstance(v, ast.Constant) and v.value is False):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, offenders
