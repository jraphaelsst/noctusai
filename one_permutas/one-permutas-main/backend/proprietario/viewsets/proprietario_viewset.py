from rest_framework.viewsets import ModelViewSet

from proprietario.models import Proprietario
from proprietario.serializers import ProprietarioSerializer


class ProprietarioViewSet(ModelViewSet):
    serializer_class = ProprietarioSerializer
    queryset = Proprietario.objects.all()
