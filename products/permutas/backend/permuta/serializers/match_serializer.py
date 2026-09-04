from rest_framework import serializers

from ..models import Match


class MatchListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list view - optimized for Kanban display"""
    imovel_ref = serializers.CharField(source='imovel.ref', read_only=True, allow_null=True)
    imovel_tipo = serializers.CharField(source='imovel.tipo.nome', read_only=True, allow_null=True)
    imovel_match = serializers.PrimaryKeyRelatedField(read_only=True)
    imovel_match_ref = serializers.CharField(source='imovel_match.ref', read_only=True, allow_null=True)
    imovel_match_tipo = serializers.CharField(source='imovel_match.tipo.nome', read_only=True, allow_null=True)
    imovel_match_valor = serializers.IntegerField(source='imovel_match.valor_venda', read_only=True, allow_null=True)
    imovel_match_condominio = serializers.CharField(source='imovel_match.condominio.nome', read_only=True, allow_null=True)
    imovel_match_proprietario = serializers.CharField(source='imovel_match.proprietario.nome', read_only=True, allow_null=True)
    permuta_imovel_codigo = serializers.CharField(source='permuta_imovel.codigo', read_only=True, allow_null=True)
    permuta_imovel_tipo = serializers.CharField(source='permuta_imovel.tipo.nome', read_only=True, allow_null=True)
    permuta_imovel_valor = serializers.IntegerField(source='permuta_imovel.valor', read_only=True, allow_null=True)
    permuta_imovel_cidade = serializers.CharField(source='permuta_imovel.cidade', read_only=True, allow_null=True)
    permuta_imovel_estado = serializers.CharField(source='permuta_imovel.estado', read_only=True, allow_null=True)
    permuta_imovel_proprietario = serializers.CharField(source='permuta_imovel.proprietario.nome', read_only=True, allow_null=True)
    permuta_automovel_codigo = serializers.CharField(source='permuta_automovel.codigo', read_only=True, allow_null=True)
    permuta_automovel_tipo = serializers.CharField(source='permuta_automovel.tipo.nome', read_only=True, allow_null=True)
    permuta_automovel_valor = serializers.IntegerField(source='permuta_automovel.valor', read_only=True, allow_null=True)
    permuta_automovel_marca = serializers.CharField(source='permuta_automovel.marca', read_only=True, allow_null=True)
    permuta_automovel_modelo = serializers.CharField(source='permuta_automovel.modelo', read_only=True, allow_null=True)
    permuta_automovel_proprietario = serializers.CharField(source='permuta_automovel.proprietario.nome', read_only=True, allow_null=True)
    class Meta:
        model = Match
        fields = [
            'id',
            'codigo',
            'etapa_do_funil',
            'ordem',
            'is_bilateral',
            'imovel',
            'imovel_ref',
            'imovel_tipo',
            'imovel_match',
            'imovel_match_ref',
            'imovel_match_tipo',
            'imovel_match_valor',
            'imovel_match_condominio',
            'imovel_match_proprietario',
            'permuta_imovel',
            'permuta_imovel_codigo',
            'permuta_imovel_tipo',
            'permuta_imovel_valor',
            'permuta_imovel_cidade',
            'permuta_imovel_estado',
            'permuta_imovel_proprietario',
            'permuta_automovel',
            'permuta_automovel_codigo',
            'permuta_automovel_tipo',
            'permuta_automovel_valor',
            'permuta_automovel_marca',
            'permuta_automovel_modelo',
            'permuta_automovel_proprietario',
        ]


class MatchSerializer(serializers.ModelSerializer):
    criado_por_nome = serializers.CharField(source='criado_por.username', read_only=True)
    permuta_imovel_codigo = serializers.CharField(source='permuta_imovel.codigo', read_only=True, allow_null=True)
    permuta_automovel_codigo = serializers.CharField(source='permuta_automovel.codigo', read_only=True, allow_null=True)
    imovel_ref = serializers.CharField(source='imovel.ref', read_only=True, allow_null=True)
    imovel_tipo = serializers.CharField(source='imovel.tipo.nome', read_only=True, allow_null=True)
    imovel_valor = serializers.IntegerField(source='imovel.valor_venda', read_only=True, allow_null=True)
    imovel_corretor = serializers.CharField(source='imovel.corretor', read_only=True, allow_null=True)
    imovel_match_ref = serializers.CharField(source='imovel_match.ref', read_only=True, allow_null=True)
    imovel_match_tipo = serializers.CharField(source='imovel_match.tipo.nome', read_only=True, allow_null=True)
    imovel_match_valor = serializers.IntegerField(source='imovel_match.valor_venda', read_only=True, allow_null=True)
    imovel_match_corretor = serializers.CharField(source='imovel_match.corretor', read_only=True, allow_null=True)
    imovel_match_condominio = serializers.CharField(source='imovel_match.condominio.nome', read_only=True, allow_null=True)
    imovel_match_proprietario = serializers.CharField(source='imovel_match.proprietario.nome', read_only=True, allow_null=True)
    permuta_imovel_tipo = serializers.CharField(source='permuta_imovel.tipo.nome', read_only=True, allow_null=True)
    permuta_imovel_valor = serializers.IntegerField(source='permuta_imovel.valor', read_only=True, allow_null=True)
    permuta_imovel_cidade = serializers.CharField(source='permuta_imovel.cidade', read_only=True, allow_null=True)
    permuta_imovel_estado = serializers.CharField(source='permuta_imovel.estado', read_only=True, allow_null=True)
    permuta_imovel_proprietario = serializers.CharField(source='permuta_imovel.proprietario.nome', read_only=True, allow_null=True)
    permuta_automovel_tipo = serializers.CharField(source='permuta_automovel.tipo.nome', read_only=True, allow_null=True)
    permuta_automovel_valor = serializers.IntegerField(source='permuta_automovel.valor', read_only=True, allow_null=True)
    permuta_automovel_marca = serializers.CharField(source='permuta_automovel.marca', read_only=True, allow_null=True)
    permuta_automovel_modelo = serializers.CharField(source='permuta_automovel.modelo', read_only=True, allow_null=True)
    permuta_automovel_proprietario = serializers.CharField(source='permuta_automovel.proprietario.nome', read_only=True, allow_null=True)
    etapa_do_funil_display = serializers.CharField(source='get_etapa_do_funil_display', read_only=True)
    
    class Meta:
        model = Match
        fields = [
            'id',
            'codigo',
            'permuta_imovel',
            'permuta_imovel_codigo',
            'permuta_imovel_tipo',
            'permuta_imovel_valor',
            'permuta_imovel_cidade',
            'permuta_imovel_estado',
            'permuta_imovel_proprietario',
            'permuta_automovel',
            'permuta_automovel_codigo',
            'permuta_automovel_tipo',
            'permuta_automovel_valor',
            'permuta_automovel_marca',
            'permuta_automovel_modelo',
            'permuta_automovel_proprietario',
            'imovel',
            'imovel_ref',
            'imovel_tipo',
            'imovel_valor',
            'imovel_corretor',
            'imovel_match',
            'imovel_match_ref',
            'imovel_match_tipo',
            'imovel_match_valor',
            'imovel_match_corretor',
            'imovel_match_condominio',
            'imovel_match_proprietario',
            'interesse_imovel',
            'interesse_automovel',
            'etapa_do_funil',
            'etapa_do_funil_display',
            'ordem',
            'observacoes',
            'criado_por',
            'criado_por_nome',
            'criado_em',
            'atualizado_em',
        ]
        read_only_fields = ['id', 'codigo', 'criado_por', 'criado_em', 'atualizado_em']
