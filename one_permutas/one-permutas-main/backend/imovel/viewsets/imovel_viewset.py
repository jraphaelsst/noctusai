from rest_framework.viewsets import ModelViewSet

from imovel.models import Imovel
from imovel.serializers import ImovelSerializer


class ImovelViewSet(ModelViewSet):
    serializer_class = ImovelSerializer
    queryset = Imovel.objects.all()
