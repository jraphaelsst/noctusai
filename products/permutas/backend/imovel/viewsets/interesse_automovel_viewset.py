from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated

from imovel.models import InteresseAutomovel
from imovel.serializers import InteresseAutomovelSerializer


class InteresseAutomovelViewSet(ModelViewSet):
    serializer_class = InteresseAutomovelSerializer
    queryset = InteresseAutomovel.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        imovel_id = self.request.query_params.get('imovel', None)
        if imovel_id:
            queryset = queryset.filter(imovel_id=imovel_id)
        return queryset
    
    def perform_create(self, serializer):
        interesse = serializer.save()
        from permuta.tasks import sync_matches_for_interesse_automovel
        sync_matches_for_interesse_automovel.delay(interesse.id, self.request.user.id)
