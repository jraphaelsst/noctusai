from rest_framework.serializers import CharField, ModelSerializer

from condominio.models import Condominio


class CondominioSerializer(ModelSerializer):
    criado_por_nome = CharField(source='criado_por.username', read_only=True)
    
    class Meta:
        model = Condominio
        fields = [
            'id',
            'criado_por',
            'criado_por_nome',
            'nome',
            'cep',
            'estado',
            'cidade',
            'bairro',
            'endereco',
            'numero',
            'km',
            'valor_condominio'
        ]
        extra_kwargs = {
            'criado_por': {'required': True},
            'nome': {'required': False, 'allow_blank': True, 'allow_null': True},
            'cep': {'required': False, 'allow_blank': True, 'allow_null': True},
            'estado': {'required': False, 'allow_blank': True, 'allow_null': True},
            'cidade': {'required': False, 'allow_blank': True, 'allow_null': True},
            'bairro': {'required': False, 'allow_blank': True, 'allow_null': True},
            'endereco': {'required': False, 'allow_blank': True, 'allow_null': True},
            'numero': {'required': False, 'allow_null': True},
            'km': {'required': False, 'allow_null': True},
            'valor_condominio': {'required': False, 'allow_null': True}
        }
