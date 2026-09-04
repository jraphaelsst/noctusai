from rest_framework.serializers import CharField, ModelSerializer, SerializerMethodField

from permuta.models import PermutaImovel


class PermutaImovelListSerializer(ModelSerializer):
    """Serializer leve para listagem - sem campos pesados de relacionamento"""
    tipo_nome = CharField(source='tipo.nome', read_only=True, allow_null=True)
    zona_nome = CharField(source='zona.nome', read_only=True, allow_null=True)
    proprietario_nome = CharField(source='proprietario.nome', read_only=True)
    
    class Meta:
        model = PermutaImovel
        fields = ['id', 'codigo', 'ref', 'tipo', 'tipo_nome', 'zona', 'zona_nome', 'estado', 
                  'bairro', 'valor', 'proprietario', 'proprietario_nome']


class PermutaImovelSerializer(ModelSerializer):
    tipo_nome = CharField(source='tipo.nome', read_only=True, allow_null=True)
    zona_nome = CharField(source='zona.nome', read_only=True, allow_null=True)
    corretor_nome = CharField(source='corretor.nome', read_only=True, allow_null=True)
    criado_por_nome = CharField(source='criado_por.username', read_only=True)
    proprietario_nome = CharField(source='proprietario.nome', read_only=True)
    imoveis_interessados = SerializerMethodField()
    
    class Meta:
        model = PermutaImovel
        fields = ['id', 'codigo', 'ref', 'proprietario', 'proprietario_nome', 'criado_por', 'criado_por_nome', 'corretor', 'corretor_nome', 'tipo', 'tipo_nome', 'condominio', 'zona', 'zona_nome', 'cep', 'estado', 'cidade', 'bairro', 'endereco', 'numero', 'valor', 'imoveis_interessados']
        read_only_fields = ['codigo']
        extra_kwargs = {
            'criado_por': {'required': False, 'read_only': True},
            'proprietario': {'required': False, 'allow_null': True},
            'corretor': {'required': False, 'allow_null': True},
            'tipo': {'required': False, 'allow_null': True},
            'zona': {'required': False, 'allow_null': True},
            'ref': {'required': False, 'allow_blank': True, 'allow_null': True},
            'condominio': {'required': False, 'allow_null': True},
            'cep': {'required': False, 'allow_blank': True},
            'estado': {'required': False, 'allow_blank': True},
            'cidade': {'required': False, 'allow_blank': True},
            'bairro': {'required': False, 'allow_blank': True},
            'endereco': {'required': False, 'allow_blank': True},
            'numero': {'required': False, 'allow_null': True},
            'valor': {'required': False, 'allow_null': True}
        }
    
    def get_imoveis_interessados(self, obj):
        from permuta.models import Match
        
        matches = Match.objects.filter(
            permuta_imovel=obj
        ).select_related(
            'imovel', 'imovel__tipo', 'imovel__zona',
            'imovel__condominio', 'imovel__proprietario'
        )
        
        seen_ids = set()
        result = []
        for match in matches:
            im = match.imovel
            if im.id not in seen_ids:
                seen_ids.add(im.id)
                result.append({
                    'id': im.id,
                    'ref': im.ref,
                    'tipo_nome': im.tipo.nome if im.tipo else None,
                    'zona_nome': im.zona.nome if im.zona else None,
                    'valor_venda': im.valor_venda,
                    'condominio_nome': im.condominio.nome if im.condominio else None,
                    'condominio_bairro': im.condominio.bairro if im.condominio else None,
                    'proprietario_nome': im.proprietario.nome if im.proprietario else None
                })
        return result
