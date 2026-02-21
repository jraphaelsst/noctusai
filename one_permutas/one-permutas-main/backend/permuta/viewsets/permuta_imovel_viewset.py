from rest_framework.viewsets import ModelViewSet

from permuta.models import PermutaImovel
from permuta.serializers import PermutaImovelSerializer


class PermutaImovelViewSet(ModelViewSet):
    serializer_class = PermutaImovelSerializer
    queryset = PermutaImovel.objects.all()
