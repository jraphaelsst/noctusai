from rest_framework.serializers import CharField, ModelSerializer
from zona.models import Zona


class ZonaSerializer(ModelSerializer):
    criado_por_nome = CharField(source='criado_por.username', read_only=True)
    
    class Meta:
        model = Zona
        fields = ['id', 'criado_por', 'criado_por_nome', 'nome', 'descricao', 'criado_em']
        extra_kwargs = {
            'nome': {'required': True},
            'descricao': {'required': False, 'allow_blank': True}
        }
        read_only_fields = ['criado_em', 'criado_por']
