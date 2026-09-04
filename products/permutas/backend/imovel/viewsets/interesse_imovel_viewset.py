from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated

from imovel.models import InteresseImovel
from imovel.serializers import InteresseImovelSerializer


class InteresseImovelViewSet(ModelViewSet):
    serializer_class = InteresseImovelSerializer
    queryset = InteresseImovel.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        imovel_id = self.request.query_params.get('imovel', None)
        if imovel_id:
            queryset = queryset.filter(imovel_id=imovel_id)
        return queryset
    
    def perform_create(self, serializer):
        interesse = serializer.save()
        from permuta.tasks import sync_matches_for_interesse_imovel
        sync_matches_for_interesse_imovel.delay(interesse.id, self.request.user.id)
