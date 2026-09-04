from rest_framework.serializers import CharField, ModelSerializer
from corretor.models import Corretor


class CorretorSerializer(ModelSerializer):
    criado_por_nome = CharField(source='criado_por.username', read_only=True)
    
    class Meta:
        model = Corretor
        fields = ['id', 'criado_por', 'criado_por_nome', 'nome', 'telefone', 'email', 'creci', 'criado_em']
        extra_kwargs = {
            'nome': {'required': True},
            'telefone': {'required': False, 'allow_blank': True},
            'email': {'required': False, 'allow_blank': True},
            'creci': {'required': False, 'allow_blank': True}
        }
        read_only_fields = ['criado_em', 'criado_por']
