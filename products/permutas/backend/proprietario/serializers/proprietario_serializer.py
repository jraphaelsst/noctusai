from rest_framework.serializers import CharField, ModelSerializer

from proprietario.models import Proprietario


class ProprietarioSerializer(ModelSerializer):
    criado_por_nome = CharField(source='user.username', read_only=True)
    corretor_nome = CharField(source='corretor.nome', read_only=True, allow_null=True)
    
    class Meta:
        model = Proprietario
        fields = ['id', 'criado_por', 'criado_por_nome', 'corretor', 'corretor_nome', 'nome', 'telefone', 'email']
        extra_kwargs = {
            'criado_por': {
                'required': True
            },
            'corretor': {
                'required': False,
                'allow_null': True
            },
            'nome': {
                'required': True
            },
            'telefone': {
                'required': True
            },
            'email': {
                'required': False,
                'allow_blank': True
            }
        }
