from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from corretor.models import Corretor
from corretor.serializers import CorretorSerializer


class CorretorViewSet(ModelViewSet):
    serializer_class = CorretorSerializer
    queryset = Corretor.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = None
    
    def get_queryset(self):
        queryset = Corretor.objects.all()
        search = self.request.query_params.get('search', None)
        
        if search:
            queryset = queryset.filter(
                Q(nome__icontains=search) |
                Q(email__icontains=search) |
                Q(creci__icontains=search)
            )
        
        nome = self.request.query_params.get('nome')
        telefone = self.request.query_params.get('telefone')
        email = self.request.query_params.get('email')
        creci = self.request.query_params.get('creci')
        
        if nome:
            queryset = queryset.filter(nome__icontains=nome)
        if telefone:
            queryset = queryset.filter(telefone__icontains=telefone)
        if email:
            queryset = queryset.filter(email__icontains=email)
        if creci:
            queryset = queryset.filter(creci__icontains=creci)
        
        return queryset.order_by('nome')
    
    def perform_create(self, serializer):
        serializer.save(criado_por=self.request.user)
