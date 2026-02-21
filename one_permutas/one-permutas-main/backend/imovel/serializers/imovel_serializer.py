from rest_framework.serializers import CharField, ChoiceField, ModelSerializer

from imovel.models import Imovel


class ImovelSerializer(ModelSerializer):
    tipo = ChoiceField(choices=Imovel.choices_tipo)
    
    criado_por_nome = CharField(source='user.username', read_only=True)
    
    condominio_nome = CharField(source='condominio.nome', read_only=True)
    condominio_bairro = CharField(source='condominio.bairro', read_only=True)
    condominio_km = CharField(source='condominio.km', read_only=True)
    condominio_endereco = CharField(source='condominio.endereco', read_only=True)
    
    proprietario_nome = CharField(source='proprietario.nome', read_only=True)
    proprietario_telefone = CharField(source='proprietario.telefone', read_only=True)
    proprietario_email = CharField(source='proprietario.email', read_only=True)
    
    class Meta:
        model = Imovel
        fields = '__all__'
