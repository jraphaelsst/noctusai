from rest_framework.viewsets import ModelViewSet

from condominio.models import Condominio
from condominio.serializers import CondominioSerializer


class CondominioViewSet(ModelViewSet):
    serializer_class = CondominioSerializer
    queryset = Condominio.objects.all()
