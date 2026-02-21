from rest_framework.serializers import CharField, ChoiceField, ModelSerializer

from permuta.models import PermutaImovel

class PermutaImovelSerializer(ModelSerializer):
    tipo = ChoiceField(choices=PermutaImovel.choices_tipo)
    zona = ChoiceField(choices=PermutaImovel.choices_zona)
    criado_por_nome = CharField(source='user.username', read_only=True)
    proprietario_nome = CharField(source='proprietario.nome', read_only=True)
    
    class Meta:
        model = PermutaImovel
        fields = ['id', 'proprietario', 'proprietario_nome', 'criado_por', 'criado_por_nome', 'corretor', 'tipo', 'condominio', 'zona', 'cep', 'estado', 'cidade', 'bairro', 'endereco', 'numero', 'valor']
        extra_kwargs = {
            'criado_por': {
                'required': True
            },
            'corretor': {
                'required': True
            },
            'proprietario': {
                'required': True
            },
            'tipo': {
                'required': True
            },
            'condominio': {
                'required': True
            },
            'zona': {
                'required': True
            },
            'cep': {
                'required': True
            },
            'estado': {
                'required': True
            },
            'cidade': {
                'required': True
            },
            'bairro': {
                'required': True
            },
            'endereco': {
                'required': True
            },
            'valor': {
                'required': True
            }
        }
