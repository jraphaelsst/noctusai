"""`/api/favorecidos*` and the card selection route — strict `== 401`, never
`in (401, 404|422)` (a permissive tuple is a false-green: route-absent or
validation-before-auth both pass it).
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`
"""
from __future__ import annotations

from uuid import uuid4

_ID = str(uuid4())
_CLIENTE = str(uuid4())

_ROUTES: tuple[tuple[str, str], ...] = (
    ("get", "/api/card-hub/favorecidos"),
    ("get", "/api/card-hub/favorecidos/{id}"),
    ("post", "/api/card-hub/favorecidos"),
    ("patch", "/api/card-hub/favorecidos/{id}"),
    ("delete", "/api/card-hub/favorecidos/{id}"),
    ("put", "/api/card-hub/atendimentos/{cliente_id}/favorecidos/selecao"),
)


def test_every_favorecidos_route_requires_auth(anon_client):
    for method, path in _ROUTES:
        concrete = path.replace("{id}", _ID).replace("{cliente_id}", _CLIENTE)
        kwargs = {}
        if method in ("post", "patch", "put"):
            kwargs["json"] = {"favorecido_id": _ID} if method == "put" else {"nome": "x"}
        r = getattr(anon_client, method)(concrete, **kwargs)
        assert r.status_code == 401, (method, path, r.status_code)
