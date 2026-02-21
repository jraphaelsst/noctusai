from rest_framework.serializers import CharField, ModelSerializer

from condominio.models import Condominio


class CondominioSerializer(ModelSerializer):
    criado_por_nome = CharField(source='user.username', read_only=True)
    
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
            'criado_por': {
                'required': True
            },
            'nome': {
                'required': True
            },
            'cep': {
                'required': True
            },
            'endereco': {
                'required': True
            },
            'numero': {
                'required': True
            },
            'km': {
                'required': True
            }
        }
