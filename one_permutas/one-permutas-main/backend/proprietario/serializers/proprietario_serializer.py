from rest_framework.serializers import CharField, ModelSerializer

from proprietario.models import Proprietario


class ProprietarioSerializer(ModelSerializer):
    criado_por_nome = CharField(source='user.username', read_only=True)
    
    class Meta:
        model = Proprietario
        fields = ['id', 'criado_por', 'criado_por_nome', 'corretor', 'nome', 'telefone', 'email']
        extra_kwargs = {
            'criado_por': {
                'required': True
            },
            'corretor': {
                'required': True
            },
            'nome': {
                'required': True
            },
            'telefone': {
                'required': True
            },
            'email': {
                'required': True
            }
        }
