"""The SW WAHA line list is DERIVED from the generated seed module (itself rendered from deploy/fleet/waha-instances.yml)."""
from pathlib import Path

from app.waha_instances import PRODUCT, get_waha_instances, instances_from_lines

YML = Path(__file__).resolve().parents[4] / "deploy" / "fleet" / "waha-instances.yml"


def test_provisioning_list_is_only_this_products_declared_lines():
    from noctusai_lib.integrations.whatsapp.declared_lines import DECLARED_LINES

    names = {i.name for i in get_waha_instances()}
    assert names == {n for n, r in DECLARED_LINES.items() if r["product"] == PRODUCT}
    assert names, "social-wiring declares at least the shared line"


def test_list_matches_the_yml_when_present():
    if not YML.is_file():
        return
    import yaml

    declared = {i["name"] for i in yaml.safe_load(YML.read_text(encoding="utf-8"))["instances"] if i.get("product") == PRODUCT}
    assert declared <= {i.name for i in get_waha_instances()}


def test_derivation_keeps_only_this_products_rows_and_env_names():
    lines = {
        "a": {"product": PRODUCT, "base_url": "http://waha-a:3000/", "session": "default", "api_key_env": "WAHA_A_API_KEY",
              "hmac_secret_env": "WAHA_A_HMAC_SECRET", "shared": False},
        "b": {"product": "assistant", "base_url": "http://waha-b:3000", "session": "default", "api_key_env": "X", "hmac_secret_env": "Y"},
    }
    got = instances_from_lines(lines)
    assert [(i.name, i.base_url, i.api_key_env, i.hmac_env) for i in got] == [
        ("a", "http://waha-a:3000", "WAHA_A_API_KEY", "WAHA_A_HMAC_SECRET")
    ]
