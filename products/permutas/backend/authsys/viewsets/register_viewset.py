from rest_framework.mixins import CreateModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from authsys.models import User
from authsys.serializers import RegisterSerializer


class RegisterViewSet(CreateModelMixin, GenericViewSet):
    """Create a user account. Authenticated, create-only.

    Previously a full ``ModelViewSet`` with ``AllowAny``, which handed anonymous
    callers the whole user table: ``GET /api/register/`` listed every account
    (enumeration) and ``PATCH/DELETE /api/register/<pk>/`` could overwrite or
    remove one — including changing an existing user's password (takeover).

    Narrowed to ``CreateModelMixin`` so ONLY the POST list-route is routed; the
    list/retrieve/update/destroy routes no longer exist (405). Account creation
    is an internal action performed by a logged-in user — the SPA has no public
    signup route (``pages/Cadastro`` is not wired into ``routes.tsx``).
    """

    permission_classes = [IsAuthenticated]

    serializer_class = RegisterSerializer
    queryset = User.objects.all()
