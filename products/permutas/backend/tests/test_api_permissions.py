"""API authorization boundary — regression guard.

Born from a live exposure (2026-08-26): `REST_FRAMEWORK` declared no
`DEFAULT_PERMISSION_CLASSES`, so DRF's built-in default (`AllowAny`) applied to
every viewset that omitted the attribute. `condominio`, `imovel` and
`proprietario` are full `ModelViewSet`s, so anonymous callers on the public
internet could list, create, update AND delete real property/owner records;
`/api/register/` additionally leaked the whole user table and allowed password
overwrite on an existing account.

These tests assert the boundary itself, not the individual viewsets — a NEW
viewset that forgets `permission_classes` is caught by `test_anonymous_is_denied`
only if it is listed here, so `test_no_viewset_opts_into_allowany` provides the
static backstop for the ones nobody remembered to add.
"""
import ast
import pathlib

import pytest
from django.urls import reverse
from rest_framework import status

# Every data endpoint that must require authentication.
PROTECTED_LIST_ENDPOINTS = [
    '/api/condominio/',
    '/api/corretor/',
    '/api/imovel/',
    '/api/imovel/interesse/imovel/',
    '/api/imovel/interesse/automovel/',
    '/api/proprietario/',
    '/api/permuta/imovel/',
    '/api/permuta/automovel/',
    '/api/permuta/match/',
    '/api/permuta/interesse-imovel/',
    '/api/permuta/interesse-automovel/',
    '/api/zona/',
    '/api/tipo-imovel/',
    '/api/tipo-automovel/',
]


@pytest.mark.django_db
@pytest.mark.parametrize('endpoint', PROTECTED_LIST_ENDPOINTS)
def test_anonymous_read_is_denied(api_client, endpoint):
    """An unauthenticated GET must be rejected — never 200 with real rows."""
    response = api_client.get(endpoint)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
        f'{endpoint} returned {response.status_code} to an anonymous caller'
    )


@pytest.mark.django_db
@pytest.mark.parametrize('endpoint', PROTECTED_LIST_ENDPOINTS)
def test_anonymous_write_is_denied(api_client, endpoint):
    """Anonymous POST must be rejected BEFORE any validation runs.

    A 400 here would mean the request reached the serializer — i.e. the caller
    held write permission and merely sent a bad body.
    """
    response = api_client.post(endpoint, {}, format='json')
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
        f'{endpoint} accepted an anonymous write attempt ({response.status_code})'
    )


@pytest.mark.django_db
def test_authenticated_read_is_allowed(authenticated_client):
    """The lockdown must not over-reach — a logged-in user still reads."""
    for endpoint in PROTECTED_LIST_ENDPOINTS:
        response = authenticated_client.get(endpoint)
        assert response.status_code == status.HTTP_200_OK, (
            f'{endpoint} denied an authenticated user ({response.status_code})'
        )


@pytest.mark.django_db
def test_token_endpoint_stays_public(api_client):
    """Login must remain reachable without a token, or nobody can ever log in.

    An empty body must yield 400 (validation) — a 401 would mean the permission
    layer rejected it, which would lock every user out of the app.
    """
    response = api_client.post('/api/token/', {}, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_token_endpoint_rejects_bad_credentials(api_client):
    response = api_client.post(
        '/api/token/',
        {'email': 'nobody@example.com', 'password': 'wrong'},
        format='json',
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_register_does_not_expose_the_user_table(api_client, user):
    """`GET /api/register/` must not enumerate accounts.

    405 = the list route is no longer routed (create-only viewset).
    401 = routed but auth-gated. Either is acceptable; 200 is the bug.
    """
    response = api_client.get('/api/register/')
    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_405_METHOD_NOT_ALLOWED,
    ), f'anonymous user enumeration is possible ({response.status_code})'


@pytest.mark.django_db
def test_register_detail_routes_are_gone(authenticated_client, user):
    """No update/destroy route on the user table — that was the takeover path."""
    response = authenticated_client.patch(
        f'/api/register/{user.pk}/', {'password': 'hijacked-pass-123'}, format='json'
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_anonymous_cannot_create_an_account(api_client):
    response = api_client.post(
        '/api/register/',
        {
            'username': 'intruder',
            'email': 'intruder@example.com',
            'password': 'Str0ng-Pass-123',
            'password2': 'Str0ng-Pass-123',
        },
        format='json',
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_default_permission_is_deny():
    """The setting itself is the mechanism — assert it directly."""
    from django.conf import settings

    configured = settings.REST_FRAMEWORK.get('DEFAULT_PERMISSION_CLASSES')
    assert configured, 'REST_FRAMEWORK has no DEFAULT_PERMISSION_CLASSES → DRF falls back to AllowAny'
    assert 'IsAuthenticated' in ''.join(configured)


def test_no_viewset_opts_into_allowany():
    """Static backstop for viewsets this file does not enumerate.

    `AllowAny` is never correct in this app: the only public endpoints are the
    simplejwt token views, which opt out via `permission_classes = ()` upstream.

    Parsed with `ast` rather than grepped — a substring scan also matches the
    word inside comments and docstrings (including the one in this module and in
    `register_viewset`, which describe the vulnerability being guarded against).
    Only a real code reference counts.
    """
    backend_root = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for path in backend_root.rglob('*.py'):
        if 'venv' in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8', errors='ignore'))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            hit = (
                (isinstance(node, ast.Name) and node.id == 'AllowAny')
                or (isinstance(node, ast.Attribute) and node.attr == 'AllowAny')
                or (
                    isinstance(node, ast.ImportFrom)
                    and any(a.name == 'AllowAny' for a in node.names)
                )
            )
            if hit:
                offenders.append(f'{path.relative_to(backend_root)}:{node.lineno}')
    assert not offenders, 'AllowAny referenced in code: ' + ', '.join(sorted(set(offenders)))
