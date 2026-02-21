from rest_framework.serializers import CharField, ChoiceField, ModelSerializer

from permuta.models import PermutaAutomovel

class PermutaAutomovelSerializer(ModelSerializer):
    tipo = ChoiceField(choices=PermutaAutomovel.choices_tipo)
    motor = ChoiceField(choices=PermutaAutomovel.choices_motor)
    criado_por_nome = CharField(source='user.username', read_only=True)
    proprietario_nome = CharField(source='proprietario.nome', read_only=True)
    
    class Meta:
        model = PermutaAutomovel
        fields = ['id', 'proprietario', 'proprietario_nome', 'criado_por', 'criado_por_nome', 'corretor', 'tipo', 'marca', 'modelo', 'motor', 'valor']
        extra_kwargs = {
            'criado_por': {
                'required': True
            },
            'proprietario': {
                'required': True
            },
            'corretor': {
                'required': True
            },
            'tipo': {
                'required': True
            },
            'marca': {
                'required': True
            },
            'modelo': {
                'required': True
            },
            'valor': {
                'required': True
            }
        }
