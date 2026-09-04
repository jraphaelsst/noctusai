from rest_framework.viewsets import ModelViewSet
from django.db.models import Q

from backend.throttling import SearchRateThrottle
from proprietario.models import Proprietario
from proprietario.serializers import ProprietarioSerializer


class ProprietarioViewSet(ModelViewSet):
    serializer_class = ProprietarioSerializer
    queryset = Proprietario.objects.select_related('corretor').all()
    
    def get_throttles(self):
        if self.action == 'list' and any(
            self.request.query_params.get(param) 
            for param in ['search', 'nome', 'telefone', 'email', 'corretor']
        ):
            return [SearchRateThrottle()]
        return super().get_throttles()
    
    def get_queryset(self):
        queryset = Proprietario.objects.select_related('corretor').all()
        search = self.request.query_params.get('search', None)
        
        if search:
            queryset = queryset.filter(
                Q(nome__icontains=search) |
                Q(telefone__icontains=search) |
                Q(email__icontains=search)
            )
        
        if self.action == 'list':
            nome = self.request.query_params.get('nome')
            telefone = self.request.query_params.get('telefone')
            email = self.request.query_params.get('email')
            corretor = self.request.query_params.get('corretor')
            
            if nome:
                queryset = queryset.filter(nome__icontains=nome)
            if telefone:
                queryset = queryset.filter(telefone__icontains=telefone)
            if email:
                queryset = queryset.filter(email__icontains=email)
            if corretor:
                queryset = queryset.filter(corretor__nome__icontains=corretor)
        
        return queryset
