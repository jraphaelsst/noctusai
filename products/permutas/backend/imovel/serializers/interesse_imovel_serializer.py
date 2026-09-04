from rest_framework.serializers import ModelSerializer, CharField

from imovel.models import InteresseImovel


class InteresseImovelSerializer(ModelSerializer):
    tipo_imovel_nome = CharField(source='tipo_imovel.nome', read_only=True, allow_null=True)
    zona_nome = CharField(source='zona.nome', read_only=True, allow_null=True)
    
    class Meta:
        model = InteresseImovel
        fields = '__all__'
        read_only_fields = ['criado_em', 'atualizado_em']
        extra_kwargs = {
            'imovel': {'required': False},
            'criado_por': {'required': False},
        }
