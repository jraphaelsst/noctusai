"""The plumbing every organ shares (`noctusai_lib.domain._organ_common`)."""
from __future__ import annotations

import pytest

from noctusai_lib.domain._organ_common import (
    OrganError,
    csv_safe,
    definer_search_path,
    error_factories,
    like_term,
    like_term_wildcard,
    mask_doc,
    org_rls,
)
from noctusai_lib.domain.finance.errors import FinanceError
from noctusai_lib.domain.inventory.errors import InventoryError
from noctusai_lib.domain.items.errors import ItemsError
from noctusai_lib.domain.parties.errors import PartiesError


@pytest.mark.parametrize("lead", ["=", "+", "-", "@", "\t", "\r", "＝", "＋", "－", "＠"])
def test_csv_safe_neutralises_every_formula_lead(lead):
    assert csv_safe(f"{lead}HYPERLINK(1)") == f"'{lead}HYPERLINK(1)"


@pytest.mark.parametrize("pad", [" ", "  ", " ", "　", " \t "])
def test_csv_safe_neutralises_leads_hidden_behind_whitespace(pad):
    assert csv_safe(f"{pad}=1+1").startswith("'")
    assert csv_safe(f"{pad}＝1+1").startswith("'")


def test_csv_safe_leaves_ordinary_text_alone():
    assert csv_safe("Mensalidade = outubro") == "Mensalidade = outubro"
    assert csv_safe("  ") == "  " and csv_safe(None) == "" and csv_safe(12) == "12"


def test_like_term_variants():
    assert like_term('ac"me, (x).y%_*\\').strip("%") == "ac me   x  y"
    assert like_term_wildcard('ac"me, (x).y%_*\\') == "%ac%me% %x%y%"
    assert like_term_wildcard("A.B") == "%A%B%"


def test_mask_doc():
    assert mask_doc("52998224725") == "***.982.247-**"
    assert mask_doc("11222333000181") == "**.***.333/0001-**"
    assert mask_doc(None) is None and mask_doc("123") == "***"


def test_org_rls_grants_are_opt_in():
    base = org_rls("s", "t", "public.current_org_id_for('s')")
    assert "ENABLE ROW LEVEL SECURITY" in base and '"t_select_own_org"' in base and "service_role_bypass" in base
    assert "GRANT" not in base
    granted = org_rls("s", "t", "x", grants=True)
    assert granted.startswith(org_rls("s", "t", "x")) and "GRANT SELECT ON s.t TO authenticated;" in granted


def test_definer_search_path_is_catalog_first_and_temp_last():
    assert definer_search_path("erp") == "SET search_path = pg_catalog, erp, pg_temp"
    with pytest.raises(ValueError):
        definer_search_path(" ")


def test_error_factories_bind_to_the_organ_class():
    for cls in (FinanceError, ItemsError, PartiesError, InventoryError):
        assert issubclass(cls, OrganError)
    inv, con = error_factories(ItemsError)
    e = inv("sku", "ruim", code="sku_invalido")
    assert isinstance(e, ItemsError) and e.status_code == 422 and e.details["field"] == "sku"
    c = con("dup", "ja existe", id="1")
    assert isinstance(c, ItemsError) and c.status_code == 409 and c.details == {"id": "1"}
