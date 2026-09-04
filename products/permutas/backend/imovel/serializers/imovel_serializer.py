from rest_framework.serializers import CharField, ModelSerializer, SerializerMethodField

from imovel.models import Imovel, InteresseImovel, InteresseAutomovel


class ImovelListSerializer(ModelSerializer):
    """Serializer leve para listagem - sem campos pesados de relacionamento"""
    tipo_nome = CharField(source='tipo.nome', read_only=True, allow_null=True)
    zona_nome = CharField(source='zona.nome', read_only=True, allow_null=True)
    condominio_nome = CharField(source='condominio.nome', read_only=True)
    condominio_bairro = CharField(source='condominio.bairro', read_only=True)
    proprietario_nome = CharField(source='proprietario.nome', read_only=True)
    
    class Meta:
        model = Imovel
        fields = ['id', 'ref', 'tipo', 'tipo_nome', 'zona', 'zona_nome', 'valor_venda', 
                  'condominio', 'condominio_nome', 'condominio_bairro', 
                  'proprietario', 'proprietario_nome']


class InteresseImovelReadSerializer(ModelSerializer):
    tipo_imovel_nome = CharField(source='tipo_imovel.nome', read_only=True, allow_null=True)
    zona_nome = CharField(source='zona.nome', read_only=True, allow_null=True)
    
    class Meta:
        model = InteresseImovel
        fields = ['id', 'tipo_imovel', 'tipo_imovel_nome', 'estado', 'zona', 'zona_nome', 'valor_minimo', 'valor_maximo', 'observacoes']


class InteresseAutomovelReadSerializer(ModelSerializer):
    tipo_automovel_nome = CharField(source='tipo_automovel.nome', read_only=True, allow_null=True)
    
    class Meta:
        model = InteresseAutomovel
        fields = ['id', 'tipo_automovel', 'tipo_automovel_nome', 'valor_minimo', 'valor_maximo']


class ImovelSerializer(ModelSerializer):
    tipo_nome = CharField(source='tipo.nome', read_only=True, allow_null=True)
    zona_nome = CharField(source='zona.nome', read_only=True, allow_null=True)
    corretor_nome = CharField(source='corretor.nome', read_only=True, allow_null=True)
    
    criado_por_nome = CharField(source='criado_por.username', read_only=True)
    
    condominio_nome = CharField(source='condominio.nome', read_only=True)
    condominio_bairro = CharField(source='condominio.bairro', read_only=True)
    condominio_km = CharField(source='condominio.km', read_only=True)
    condominio_endereco = CharField(source='condominio.endereco', read_only=True)
    
    proprietario_nome = CharField(source='proprietario.nome', read_only=True)
    proprietario_telefone = CharField(source='proprietario.telefone', read_only=True)
    proprietario_email = CharField(source='proprietario.email', read_only=True)
    
    interesses_imoveis_lista = SerializerMethodField()
    interesses_automoveis_lista = SerializerMethodField()
    imoveis_compativeis = SerializerMethodField()
    imoveis_interessados = SerializerMethodField()
    permutas_imoveis_compativeis = SerializerMethodField()
    permutas_automoveis_compativeis = SerializerMethodField()
    
    class Meta:
        model = Imovel
        fields = '__all__'
    
    def get_interesses_imoveis_lista(self, obj):
        interesses = obj.interesses_imoveis_rel.all()
        return InteresseImovelReadSerializer(interesses, many=True).data
    
    def get_interesses_automoveis_lista(self, obj):
        interesses = obj.interesses_automoveis_rel.all()
        return InteresseAutomovelReadSerializer(interesses, many=True).data
    
    def get_imoveis_compativeis(self, obj):
        """
        Retorna imóveis que dão match com os interesses deste imóvel.
        Busca matches do modelo Match onde este imóvel é o origem e há imovel_match.
        """
        from permuta.models import Match
        
        matches = Match.objects.filter(
            imovel=obj,
            imovel_match__isnull=False
        ).select_related(
            'imovel_match', 'imovel_match__tipo', 'imovel_match__zona',
            'imovel_match__condominio', 'imovel_match__proprietario'
        )
        
        seen_ids = set()
        result = []
        for match in matches:
            im = match.imovel_match
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
    
    def get_imoveis_interessados(self, obj):
        """
        Retorna imóveis cujos interesses correspondem a ESTE imóvel.
        Busca matches onde este imóvel é o imovel_match.
        """
        from permuta.models import Match
        
        matches = Match.objects.filter(
            imovel_match=obj
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
    
    def get_permutas_imoveis_compativeis(self, obj):
        """
        Retorna permutas de imóveis que dão match com os interesses deste imóvel.
        """
        from permuta.models import Match
        
        matches = Match.objects.filter(
            imovel=obj,
            permuta_imovel__isnull=False
        ).select_related(
            'permuta_imovel', 'permuta_imovel__tipo', 'permuta_imovel__zona',
            'permuta_imovel__proprietario'
        )
        
        seen_ids = set()
        result = []
        for match in matches:
            p = match.permuta_imovel
            if p.id not in seen_ids:
                seen_ids.add(p.id)
                result.append({
                    'id': p.id,
                    'codigo': p.codigo,
                    'tipo_nome': p.tipo.nome if p.tipo else None,
                    'zona_nome': p.zona.nome if p.zona else None,
                    'estado': p.estado,
                    'bairro': p.bairro,
                    'condominio': p.condominio,
                    'valor': p.valor,
                    'proprietario_nome': p.proprietario.nome if p.proprietario else None
                })
        return result
    
    def get_permutas_automoveis_compativeis(self, obj):
        """
        Retorna permutas de automóveis que dão match com os interesses deste imóvel.
        """
        from permuta.models import Match
        
        matches = Match.objects.filter(
            imovel=obj,
            permuta_automovel__isnull=False
        ).select_related(
            'permuta_automovel', 'permuta_automovel__tipo',
            'permuta_automovel__proprietario'
        )
        
        seen_ids = set()
        result = []
        for match in matches:
            p = match.permuta_automovel
            if p.id not in seen_ids:
                seen_ids.add(p.id)
                result.append({
                    'id': p.id,
                    'codigo': p.codigo,
                    'tipo_nome': p.tipo.nome if p.tipo else None,
                    'marca': p.marca,
                    'modelo': p.modelo,
                    'motor': p.motor,
                    'valor': p.valor,
                    'proprietario_nome': p.proprietario.nome if p.proprietario else None
                })
        return result
