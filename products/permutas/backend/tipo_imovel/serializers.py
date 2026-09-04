from rest_framework.serializers import CharField, ModelSerializer
from tipo_imovel.models import TipoImovel


class TipoImovelSerializer(ModelSerializer):
    criado_por_nome = CharField(source='criado_por.username', read_only=True)
    
    class Meta:
        model = TipoImovel
        fields = ['id', 'criado_por', 'criado_por_nome', 'nome', 'criado_em']
        extra_kwargs = {
            'nome': {'required': True}
        }
        read_only_fields = ['criado_em', 'criado_por']
