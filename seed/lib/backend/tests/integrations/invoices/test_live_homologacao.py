"""Opt-in live check against Focus NFe HOMOLOGACAO. Skipped without
`FOCUSNFE_TOKEN` (account token). Read-only: verifies credentials and lists
companies; never issues a document. Run to verify the UNVERIFIED payload
fields listed in focus.py before the P6 validation."""
import os

import pytest

from noctusai_lib.integrations.invoices import FocusNFeInvoiceProvider, InvoiceEnvironment

pytestmark = pytest.mark.skipif(
    not os.environ.get("FOCUSNFE_TOKEN"), reason="FOCUSNFE_TOKEN not set (live homologacao test)"
)


def test_live_verify_credentials_against_homologacao():
    focus = FocusNFeInvoiceProvider(
        account_token=os.environ["FOCUSNFE_TOKEN"], environment=InvoiceEnvironment.HOMOLOGACAO
    )
    try:
        focus.verify_credentials()
    finally:
        focus.close()
