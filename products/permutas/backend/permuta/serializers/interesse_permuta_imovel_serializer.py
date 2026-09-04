from rest_framework import serializers

from permuta.models import InteressePermutaImovel


class InteressePermutaImovelSerializer(serializers.ModelSerializer):
    tipo_imovel_nome = serializers.CharField(source='tipo_imovel.nome', read_only=True, allow_null=True)
    zona_nome = serializers.CharField(source='zona.nome', read_only=True, allow_null=True)
    permuta_imovel_codigo = serializers.CharField(source='permuta_imovel.codigo', read_only=True)
    criado_por_nome = serializers.CharField(source='criado_por.username', read_only=True)
    
    class Meta:
        model = InteressePermutaImovel
        fields = [
            'id', 'permuta_imovel', 'permuta_imovel_codigo', 
            'criado_por', 'criado_por_nome',
            'tipo_imovel', 'tipo_imovel_nome',
            'zona', 'zona_nome',
            'cep', 'estado', 'cidade', 'bairro', 'endereco',
            'valor_minimo', 'valor_maximo',
            'observacoes', 'criado_em', 'atualizado_em'
        ]
        read_only_fields = ['criado_por', 'criado_em', 'atualizado_em']
        extra_kwargs = {
            'permuta_imovel': {'required': True},
            'tipo_imovel': {'required': False, 'allow_null': True},
            'zona': {'required': False, 'allow_null': True},
            'cep': {'required': False, 'allow_blank': True},
            'estado': {'required': False, 'allow_blank': True},
            'cidade': {'required': False, 'allow_blank': True},
            'bairro': {'required': False, 'allow_blank': True},
            'endereco': {'required': False, 'allow_blank': True},
            'valor_minimo': {'required': False, 'allow_null': True},
            'valor_maximo': {'required': False, 'allow_null': True},
            'observacoes': {'required': False, 'allow_blank': True}
        }
    
    def validate(self, attrs):
        """Cross-field validation."""
        valor_minimo = attrs.get('valor_minimo')
        valor_maximo = attrs.get('valor_maximo')
        
        if valor_minimo is not None and valor_maximo is not None:
            if valor_minimo > valor_maximo:
                raise serializers.ValidationError({
                    'valor_minimo': 'O valor mínimo não pode ser maior que o valor máximo.',
                    'valor_maximo': 'O valor máximo não pode ser menor que o valor mínimo.'
                })
        
        return attrs
    
    def create(self, validated_data):
        validated_data['criado_por'] = self.context['request'].user
        return super().create(validated_data)


class InteressePermutaImovelListSerializer(serializers.ModelSerializer):
    """Serializer leve para listagem"""
    tipo_imovel_nome = serializers.CharField(source='tipo_imovel.nome', read_only=True, allow_null=True)
    zona_nome = serializers.CharField(source='zona.nome', read_only=True, allow_null=True)
    permuta_imovel_codigo = serializers.CharField(source='permuta_imovel.codigo', read_only=True)
    
    class Meta:
        model = InteressePermutaImovel
        fields = [
            'id', 'permuta_imovel', 'permuta_imovel_codigo',
            'tipo_imovel', 'tipo_imovel_nome',
            'zona', 'zona_nome',
            'valor_minimo', 'valor_maximo', 'criado_em'
        ]
