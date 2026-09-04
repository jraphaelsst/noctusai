from rest_framework.serializers import ModelSerializer, CharField

from imovel.models import InteresseAutomovel


class InteresseAutomovelSerializer(ModelSerializer):
    tipo_automovel_nome = CharField(source='tipo_automovel.nome', read_only=True, allow_null=True)
    
    class Meta:
        model = InteresseAutomovel
        fields = '__all__'
        read_only_fields = ['criado_em', 'atualizado_em']
        extra_kwargs = {
            'imovel': {'required': False},
            'criado_por': {'required': False},
        }
