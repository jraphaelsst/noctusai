"""The webhook base is the product itself: the personal live line has no edge and no webhook relay (KB § INTEGRATIONS/whatsapp.md §6a)."""
from app.routers.whatsapp_router import webhook_base_url


def test_the_webhook_is_registered_direct_to_the_product():
    assert webhook_base_url(lambda: "https://assistant.example.test/") == "https://assistant.example.test"


def test_no_relay_base_survives_in_the_router():
    import inspect

    from app.routers import whatsapp_router

    assert "webhook_relay" not in inspect.getsource(whatsapp_router).replace("no webhook relay", "")
