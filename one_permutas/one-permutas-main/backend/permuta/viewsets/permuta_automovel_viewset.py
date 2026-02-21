from rest_framework.viewsets import ModelViewSet

from permuta.models import PermutaAutomovel
from permuta.serializers import PermutaAutomovelSerializer


class PermutaAutomovelViewSet(ModelViewSet):
    serializer_class = PermutaAutomovelSerializer
    queryset = PermutaAutomovel.objects.all()
