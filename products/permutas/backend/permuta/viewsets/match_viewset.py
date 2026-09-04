from django.core.cache import cache
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import Match, InteressePermutaImovel, InteressePermutaAutomovel
from ..serializers import MatchSerializer, MatchListSerializer
from ..utils import generate_sequential_code
from imovel.models import InteresseImovel, InteresseAutomovel


class MatchViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Match management.
    
    IMPORTANT: By default, only returns BILATERAL matches where both sides 
    have interests registered. Use ?include_unilateral=true to see all matches.
    """
    queryset = Match.objects.all()
    serializer_class = MatchSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    
    def get_serializer_class(self):
        if self.action == 'list':
            return MatchListSerializer
        return MatchSerializer
    
    def get_queryset(self):
        """
        Return only BILATERAL matches by default.
        
        A match is bilateral if is_bilateral=True (set when match is created
        by the bilateral matching system).
        """
        queryset = Match.objects.select_related(
            'imovel',
            'imovel__tipo',
            'imovel__zona',
            'imovel__condominio',
            'imovel__proprietario',
            'imovel__corretor',
            'imovel_match',
            'imovel_match__tipo',
            'imovel_match__zona',
            'imovel_match__condominio',
            'imovel_match__proprietario',
            'imovel_match__corretor',
            'permuta_imovel',
            'permuta_imovel__tipo',
            'permuta_imovel__zona',
            'permuta_imovel__proprietario',
            'permuta_imovel__corretor',
            'permuta_automovel',
            'permuta_automovel__tipo',
            'permuta_automovel__proprietario',
            'permuta_automovel__corretor',
            'criado_por'
        ).prefetch_related(
            'imovel__interesses_imoveis_rel',
            'imovel__interesses_imoveis_rel__tipo_imovel',
            'imovel__interesses_imoveis_rel__zona',
            'imovel__interesses_automoveis_rel',
            'imovel__interesses_automoveis_rel__tipo_automovel',
            'imovel_match__interesses_imoveis_rel',
            'imovel_match__interesses_imoveis_rel__tipo_imovel',
            'imovel_match__interesses_imoveis_rel__zona',
            'permuta_imovel__interesses_permuta',
            'permuta_imovel__interesses_permuta__tipo_imovel',
            'permuta_imovel__interesses_permuta__zona',
            'permuta_automovel__interesses_permuta',
            'permuta_automovel__interesses_permuta__tipo_imovel',
            'permuta_automovel__interesses_permuta__zona',
        )
        
        include_unilateral = self.request.query_params.get('include_unilateral', 'false').lower() == 'true'
        
        if not include_unilateral:
            queryset = queryset.filter(is_bilateral=True)
        
        include_rejeitados = self.request.query_params.get('rejeitados', 'false').lower() == 'true'
        
        etapa = self.request.query_params.get('etapa', None)
        if etapa:
            queryset = queryset.filter(etapa_do_funil=etapa)
        elif not include_rejeitados:
            queryset = queryset.exclude(etapa_do_funil='rejeitado')
        
        permuta_imovel = self.request.query_params.get('permuta_imovel', None)
        if permuta_imovel:
            queryset = queryset.filter(permuta_imovel_id=permuta_imovel)
        
        permuta_automovel = self.request.query_params.get('permuta_automovel', None)
        if permuta_automovel:
            queryset = queryset.filter(permuta_automovel_id=permuta_automovel)
        
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(codigo__icontains=search)
        
        return queryset.order_by('etapa_do_funil', 'ordem', '-criado_em')
    
    def perform_create(self, serializer):
        codigo = generate_sequential_code('MT', Match)
        
        is_bilateral = False
        validated_data = serializer.validated_data
        
        imovel = validated_data.get('imovel')
        permuta_imovel = validated_data.get('permuta_imovel')
        permuta_automovel = validated_data.get('permuta_automovel')
        imovel_match = validated_data.get('imovel_match')
        
        if imovel and permuta_imovel:
            forward_exists = InteresseImovel.objects.filter(
                imovel=imovel, 
                permuta_imovel=permuta_imovel
            ).exists()
            reverse_exists = InteressePermutaImovel.objects.filter(
                permuta_imovel=permuta_imovel
            ).filter(
                tipo__isnull=True
            ).exists() or InteressePermutaImovel.objects.filter(
                permuta_imovel=permuta_imovel,
                tipo=imovel.tipo
            ).exists()
            is_bilateral = forward_exists and reverse_exists
        elif imovel and permuta_automovel:
            forward_exists = InteresseAutomovel.objects.filter(
                imovel=imovel,
                permuta_automovel=permuta_automovel
            ).exists()
            reverse_exists = InteressePermutaAutomovel.objects.filter(
                permuta_automovel=permuta_automovel
            ).exists()
            is_bilateral = forward_exists and reverse_exists
        elif imovel and imovel_match:
            forward_exists = InteresseImovel.objects.filter(
                imovel=imovel,
                tipo=imovel_match.tipo
            ).exists() or InteresseImovel.objects.filter(
                imovel=imovel,
                tipo__isnull=True
            ).exists()
            reverse_exists = InteresseImovel.objects.filter(
                imovel=imovel_match,
                tipo=imovel.tipo
            ).exists() or InteresseImovel.objects.filter(
                imovel=imovel_match,
                tipo__isnull=True
            ).exists()
            is_bilateral = forward_exists and reverse_exists
        
        serializer.save(
            criado_por=self.request.user, 
            codigo=codigo, 
            is_bilateral=is_bilateral
        )
        self._invalidate_stats_cache()
    
    def perform_update(self, serializer):
        serializer.save()
        self._invalidate_stats_cache()
    
    def perform_destroy(self, instance):
        instance.delete()
        self._invalidate_stats_cache()
    
    def _invalidate_stats_cache(self):
        """Invalidate cached statistics when matches are modified."""
        cache.delete('match_stats_bilateral')
        cache.delete('match_unilateral_count')
    
    @action(detail=False, methods=['post'])
    def sync(self, request):
        """
        Sync matches using BILATERAL matching logic.
        Only creates matches when both sides have compatible interests.
        
        IMPORTANT: Bilateral matching requires BOTH sides to have interests:
        - Forward: InteresseImovel/InteresseAutomovel (property wants something)
        - Reverse: InteressePermutaImovel/InteressePermutaAutomovel (permuta accepts something)
        
        If there are no reverse interests, no bilateral matches can be created.
        """
        from ..bilateral_matching import (
            create_bilateral_matches_for_interesse_permuta_imovel,
            create_bilateral_matches_for_interesse_permuta_automovel
        )
        
        created_count = 0
        
        reverse_imovel_count = InteressePermutaImovel.objects.count()
        reverse_automovel_count = InteressePermutaAutomovel.objects.count()
        
        if reverse_imovel_count == 0 and reverse_automovel_count == 0:
            return Response({
                'status': 'warning',
                'created': 0,
                'message': 'Nenhum interesse reverso cadastrado. Para criar matches bilaterais, cadastre interesses nas permutas (o que o dono da permuta aceita em troca).',
                'forward_interests': InteresseImovel.objects.count() + InteresseAutomovel.objects.count(),
                'reverse_interests': 0
            })
        
        interesses_permuta_imovel = InteressePermutaImovel.objects.select_related('permuta_imovel').all()
        for interesse in interesses_permuta_imovel:
            created_count += create_bilateral_matches_for_interesse_permuta_imovel(interesse, request.user)
        
        interesses_permuta_automovel = InteressePermutaAutomovel.objects.select_related('permuta_automovel').all()
        for interesse in interesses_permuta_automovel:
            created_count += create_bilateral_matches_for_interesse_permuta_automovel(interesse, request.user)
        
        return Response({
            'status': 'success',
            'created': created_count,
            'message': f'{created_count} matches bilaterais criados',
            'forward_interests': InteresseImovel.objects.count() + InteresseAutomovel.objects.count(),
            'reverse_interests': reverse_imovel_count + reverse_automovel_count
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Return statistics about bilateral matches only. Cached for 60 seconds."""
        cache_key = 'match_stats_bilateral'
        stats = cache.get(cache_key)
        
        if stats is None:
            queryset = self.get_queryset()
            stats = {
                'total': queryset.count(),
                'novo': queryset.filter(etapa_do_funil='novo').count(),
                'avaliacao': queryset.filter(etapa_do_funil='avaliacao').count(),
                'negociacao': queryset.filter(etapa_do_funil='negociacao').count(),
                'fechado': queryset.filter(etapa_do_funil='fechado').count(),
            }
            cache.set(cache_key, stats, timeout=60)
        
        return Response(stats)
    
    @action(detail=False, methods=['get'])
    def unilateral_count(self, request):
        """Return count of unilateral (old) matches that are hidden from Kanban. Cached for 60 seconds."""
        cache_key = 'match_unilateral_count'
        cached_data = cache.get(cache_key)
        
        if cached_data is None:
            unilateral_count = Match.objects.filter(is_bilateral=False).count()
            cached_data = {
                'unilateral_count': unilateral_count,
                'message': f'{unilateral_count} old matches hidden from Kanban (not bilateral)'
            }
            cache.set(cache_key, cached_data, timeout=60)
        
        return Response(cached_data)
    
    @action(detail=True, methods=['get'])
    def dossie(self, request, pk=None):
        """
        Retorna todas as informações necessárias para o dossiê do match.
        Inclui dados completos de ambas as partes para validação visual.
        
        CAMPOS CORRETOS DOS MODELOS:
        - Imovel: ref, valor_venda, tipo, zona, proprietario, corretor, condominio (FK)
        - Condominio: nome, endereco, bairro, cidade, estado, cep
        - PermutaImovel: codigo, valor, tipo, zona, endereco, bairro, cidade, estado, cep, condominio (CharField)
        - PermutaAutomovel: codigo, valor, tipo, marca, modelo, motor
        - InteresseImovel: tipo_imovel, zona, valor_minimo, valor_maximo (related_name: interesses_imoveis_rel)
        - InteresseAutomovel: tipo_automovel, valor_minimo, valor_maximo (related_name: interesses_automoveis_rel)
        - InteressePermutaImovel: tipo_imovel, zona, valor_minimo, valor_maximo (related_name: interesses_permuta)
        - InteressePermutaAutomovel: tipo_imovel, zona, valor_minimo, valor_maximo (related_name: interesses_permuta)
        - Corretor: nome (não tem get_full_name)
        """
        match = self.get_object()
        
        if not match.imovel:
            return Response(
                {'error': 'Match sem imovel associado - dados incompletos'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        parte_a = None
        parte_b = None
        tipo_match = None
        
        # PARTE A - Sempre é um Imóvel
        imovel = match.imovel
        condominio = imovel.condominio
        parte_a = {
            'tipo': 'imovel',
            'id': imovel.id,
            'ref': imovel.ref,
            'tipo_nome': imovel.tipo.nome if imovel.tipo else None,
            'endereco': condominio.endereco if condominio else None,
            'bairro': condominio.bairro if condominio else None,
            'cidade': condominio.cidade if condominio else None,
            'estado': condominio.estado if condominio else None,
            'cep': condominio.cep if condominio else None,
            'valor': float(imovel.valor_venda) if imovel.valor_venda else None,
            'zona': imovel.zona.nome if imovel.zona else None,
            'condominio': condominio.nome if condominio else None,
            'cliente': {
                'id': imovel.proprietario.id if imovel.proprietario else None,
                'nome': imovel.proprietario.nome if imovel.proprietario else None,
                'telefone': imovel.proprietario.telefone if imovel.proprietario else None,
                'email': imovel.proprietario.email if imovel.proprietario else None,
            },
            'corretor': imovel.corretor.nome if imovel.corretor else None,
        }
        
        # Interesses do Imóvel A (o que o proprietário do imóvel aceita em troca)
        interesses_a = []
        # InteresseImovel usa tipo_imovel, não tipo
        for interesse in imovel.interesses_imoveis_rel.all():
            interesses_a.append({
                'tipo': 'imovel',
                'tipo_aceito': interesse.tipo_imovel.nome if interesse.tipo_imovel else 'Qualquer tipo',
                'zona_aceita': interesse.zona.nome if interesse.zona else 'Qualquer zona',
                'valor_minimo': float(interesse.valor_minimo) if interesse.valor_minimo else None,
                'valor_maximo': float(interesse.valor_maximo) if interesse.valor_maximo else None,
            })
        # InteresseAutomovel usa tipo_automovel, não tipo
        for interesse in imovel.interesses_automoveis_rel.all():
            interesses_a.append({
                'tipo': 'automovel',
                'tipo_aceito': interesse.tipo_automovel.nome if interesse.tipo_automovel else 'Qualquer tipo',
                'valor_minimo': float(interesse.valor_minimo) if interesse.valor_minimo else None,
                'valor_maximo': float(interesse.valor_maximo) if interesse.valor_maximo else None,
            })
        parte_a['interesses'] = interesses_a
        
        # PARTE B - Pode ser PermutaImovel, PermutaAutomovel ou outro Imovel
        if match.permuta_imovel:
            tipo_match = 'imovel_permuta_imovel'
            permuta = match.permuta_imovel
            parte_b = {
                'tipo': 'permuta_imovel',
                'id': permuta.id,
                'codigo': permuta.codigo,
                'tipo_nome': permuta.tipo.nome if permuta.tipo else None,
                'endereco': permuta.endereco,
                'bairro': permuta.bairro,
                'cidade': permuta.cidade,
                'estado': permuta.estado,
                'cep': permuta.cep,
                'valor': float(permuta.valor) if permuta.valor else None,
                'zona': permuta.zona.nome if permuta.zona else None,
                'condominio': permuta.condominio,  # CharField, não FK
                'cliente': {
                    'id': permuta.proprietario.id if permuta.proprietario else None,
                    'nome': permuta.proprietario.nome if permuta.proprietario else None,
                    'telefone': permuta.proprietario.telefone if permuta.proprietario else None,
                    'email': permuta.proprietario.email if permuta.proprietario else None,
                },
                'corretor': permuta.corretor.nome if permuta.corretor else None,
            }
            
            # InteressePermutaImovel usa tipo_imovel (related_name: interesses_permuta)
            interesses_b = []
            for interesse in permuta.interesses_permuta.all():
                interesses_b.append({
                    'tipo': 'imovel',
                    'tipo_aceito': interesse.tipo_imovel.nome if interesse.tipo_imovel else 'Qualquer tipo',
                    'zona_aceita': interesse.zona.nome if interesse.zona else 'Qualquer zona',
                    'valor_minimo': float(interesse.valor_minimo) if interesse.valor_minimo else None,
                    'valor_maximo': float(interesse.valor_maximo) if interesse.valor_maximo else None,
                })
            parte_b['interesses'] = interesses_b
            
        elif match.permuta_automovel:
            tipo_match = 'imovel_permuta_automovel'
            permuta = match.permuta_automovel
            parte_b = {
                'tipo': 'permuta_automovel',
                'id': permuta.id,
                'codigo': permuta.codigo,
                'tipo_nome': permuta.tipo.nome if permuta.tipo else None,
                'marca': permuta.marca,
                'modelo': permuta.modelo,
                'motor': permuta.motor,
                'valor': float(permuta.valor) if permuta.valor else None,
                'cliente': {
                    'id': permuta.proprietario.id if permuta.proprietario else None,
                    'nome': permuta.proprietario.nome if permuta.proprietario else None,
                    'telefone': permuta.proprietario.telefone if permuta.proprietario else None,
                    'email': permuta.proprietario.email if permuta.proprietario else None,
                },
                'corretor': permuta.corretor.nome if permuta.corretor else None,
            }
            
            # InteressePermutaAutomovel usa tipo_imovel (related_name: interesses_permuta)
            interesses_b = []
            for interesse in permuta.interesses_permuta.all():
                interesses_b.append({
                    'tipo': 'imovel',
                    'tipo_aceito': interesse.tipo_imovel.nome if interesse.tipo_imovel else 'Qualquer tipo',
                    'zona_aceita': interesse.zona.nome if interesse.zona else 'Qualquer zona',
                    'valor_minimo': float(interesse.valor_minimo) if interesse.valor_minimo else None,
                    'valor_maximo': float(interesse.valor_maximo) if interesse.valor_maximo else None,
                })
            parte_b['interesses'] = interesses_b
            
        elif match.imovel_match:
            tipo_match = 'imovel_imovel'
            imovel_b = match.imovel_match
            condominio_b = imovel_b.condominio
            parte_b = {
                'tipo': 'imovel',
                'id': imovel_b.id,
                'ref': imovel_b.ref,
                'tipo_nome': imovel_b.tipo.nome if imovel_b.tipo else None,
                'endereco': condominio_b.endereco if condominio_b else None,
                'bairro': condominio_b.bairro if condominio_b else None,
                'cidade': condominio_b.cidade if condominio_b else None,
                'estado': condominio_b.estado if condominio_b else None,
                'cep': condominio_b.cep if condominio_b else None,
                'valor': float(imovel_b.valor_venda) if imovel_b.valor_venda else None,
                'zona': imovel_b.zona.nome if imovel_b.zona else None,
                'condominio': condominio_b.nome if condominio_b else None,
                'cliente': {
                    'id': imovel_b.proprietario.id if imovel_b.proprietario else None,
                    'nome': imovel_b.proprietario.nome if imovel_b.proprietario else None,
                    'telefone': imovel_b.proprietario.telefone if imovel_b.proprietario else None,
                    'email': imovel_b.proprietario.email if imovel_b.proprietario else None,
                },
                'corretor': imovel_b.corretor.nome if imovel_b.corretor else None,
            }
            
            # InteresseImovel usa tipo_imovel
            interesses_b = []
            for interesse in imovel_b.interesses_imoveis_rel.all():
                interesses_b.append({
                    'tipo': 'imovel',
                    'tipo_aceito': interesse.tipo_imovel.nome if interesse.tipo_imovel else 'Qualquer tipo',
                    'zona_aceita': interesse.zona.nome if interesse.zona else 'Qualquer zona',
                    'valor_minimo': float(interesse.valor_minimo) if interesse.valor_minimo else None,
                    'valor_maximo': float(interesse.valor_maximo) if interesse.valor_maximo else None,
                })
            parte_b['interesses'] = interesses_b
        
        if not parte_b:
            return Response(
                {'error': 'Match sem parte B (permuta/imovel) associada - dados incompletos'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        valor_a = parte_a.get('valor', 0) or 0
        valor_b = parte_b.get('valor', 0) or 0
        diferenca = abs(valor_a - valor_b)
        quem_complementa = 'B' if valor_a > valor_b else 'A' if valor_b > valor_a else None
        
        a_oferece = parte_a.get('tipo_nome') or 'Nao especificado'
        a_aceita = [i.get('tipo_aceito') for i in parte_a.get('interesses', [])]
        b_oferece = parte_b.get('tipo_nome') or 'Nao especificado'
        b_aceita = [i.get('tipo_aceito') for i in parte_b.get('interesses', [])]
        
        a_aceita_b = any(
            b_oferece.lower() in (aceito or '').lower() or aceito == 'Qualquer tipo'
            for aceito in a_aceita
        ) if a_aceita else False
        
        b_aceita_a = any(
            a_oferece.lower() in (aceito or '').lower() or aceito == 'Qualquer tipo'
            for aceito in b_aceita
        ) if b_aceita else False
        
        # Buscar matches relacionados ao mesmo imóvel
        matches_do_imovel = Match.objects.filter(
            imovel=match.imovel,
            is_bilateral=True
        ).exclude(id=match.id).select_related(
            'permuta_imovel', 'permuta_automovel', 'imovel_match'
        )[:10]
        
        matches_imovel_list = []
        for m in matches_do_imovel:
            match_info = {
                'id': m.id,
                'codigo': m.codigo,
                'etapa_do_funil': m.etapa_do_funil,
            }
            if m.permuta_imovel:
                match_info['parte_b_tipo'] = 'permuta_imovel'
                match_info['parte_b_codigo'] = m.permuta_imovel.codigo
                match_info['parte_b_valor'] = float(m.permuta_imovel.valor) if m.permuta_imovel.valor else None
            elif m.permuta_automovel:
                match_info['parte_b_tipo'] = 'permuta_automovel'
                match_info['parte_b_codigo'] = m.permuta_automovel.codigo
                match_info['parte_b_valor'] = float(m.permuta_automovel.valor) if m.permuta_automovel.valor else None
            elif m.imovel_match:
                match_info['parte_b_tipo'] = 'imovel'
                match_info['parte_b_codigo'] = m.imovel_match.ref
                match_info['parte_b_valor'] = float(m.imovel_match.valor_venda) if m.imovel_match.valor_venda else None
            matches_imovel_list.append(match_info)
        
        # Buscar matches relacionados à mesma permuta (se aplicável)
        matches_permuta_list = []
        if match.permuta_imovel:
            matches_da_permuta = Match.objects.filter(
                permuta_imovel=match.permuta_imovel,
                is_bilateral=True
            ).exclude(id=match.id).select_related('imovel')[:10]
            
            for m in matches_da_permuta:
                matches_permuta_list.append({
                    'id': m.id,
                    'codigo': m.codigo,
                    'etapa_do_funil': m.etapa_do_funil,
                    'parte_a_tipo': 'imovel',
                    'parte_a_codigo': m.imovel.ref if m.imovel else None,
                    'parte_a_valor': float(m.imovel.valor_venda) if m.imovel and m.imovel.valor_venda else None,
                })
        elif match.permuta_automovel:
            matches_da_permuta = Match.objects.filter(
                permuta_automovel=match.permuta_automovel,
                is_bilateral=True
            ).exclude(id=match.id).select_related('imovel')[:10]
            
            for m in matches_da_permuta:
                matches_permuta_list.append({
                    'id': m.id,
                    'codigo': m.codigo,
                    'etapa_do_funil': m.etapa_do_funil,
                    'parte_a_tipo': 'imovel',
                    'parte_a_codigo': m.imovel.ref if m.imovel else None,
                    'parte_a_valor': float(m.imovel.valor_venda) if m.imovel and m.imovel.valor_venda else None,
                })
        
        data = {
            'match': {
                'id': match.id,
                'codigo': match.codigo,
                'etapa_do_funil': match.etapa_do_funil,
                'is_bilateral': match.is_bilateral,
                'observacoes': match.observacoes,
                'criado_em': match.criado_em.isoformat() if match.criado_em else None,
                'atualizado_em': match.atualizado_em.isoformat() if match.atualizado_em else None,
                'criado_por': match.criado_por.get_full_name() if match.criado_por else None,
            },
            'tipo_match': tipo_match,
            'parte_a': parte_a,
            'parte_b': parte_b,
            'criterios_validacao': {
                'a_oferece': a_oferece,
                'a_aceita': a_aceita,
                'b_oferece': b_oferece,
                'b_aceita': b_aceita,
                'a_aceita_b': a_aceita_b,
                'b_aceita_a': b_aceita_a,
                'match_valido': a_aceita_b and b_aceita_a,
            },
            'analise_financeira': {
                'valor_parte_a': valor_a,
                'valor_parte_b': valor_b,
                'diferenca': diferenca,
                'quem_complementa': quem_complementa,
            },
            'matches_relacionados': {
                'do_imovel': matches_imovel_list,
                'da_permuta': matches_permuta_list,
            },
        }
        
        return Response(data)
    
    @action(detail=True, methods=['post'])
    def adicionar_observacao(self, request, pk=None):
        """Adiciona uma observação ao match."""
        from django.utils import timezone
        match = self.get_object()
        observacao = request.data.get('observacao', '')
        
        if observacao:
            timestamp = timezone.now().strftime('%d/%m/%Y %H:%M')
            usuario = request.user.get_full_name() or request.user.username
            nova_obs = f"[{timestamp}] {usuario}: {observacao}"
            
            if match.observacoes:
                match.observacoes = f"{match.observacoes}\n{nova_obs}"
            else:
                match.observacoes = nova_obs
            match.save(update_fields=['observacoes'])
        
        return Response({'status': 'ok', 'observacoes': match.observacoes})
    
    @action(detail=True, methods=['post'])
    def avancar_etapa(self, request, pk=None):
        """Avança o match para a próxima etapa do funil."""
        match = self.get_object()
        
        if match.etapa_do_funil == 'rejeitado':
            return Response(
                {'error': 'Match rejeitado nao pode avancar. Recupere-o primeiro.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        etapas = ['novo', 'avaliacao', 'negociacao', 'fechado']
        current_idx = etapas.index(match.etapa_do_funil)
        
        if current_idx < len(etapas) - 1:
            match.etapa_do_funil = etapas[current_idx + 1]
            match.save(update_fields=['etapa_do_funil'])
            return Response({
                'status': 'ok', 
                'nova_etapa': match.etapa_do_funil,
                'etapa_label': dict(Match.ETAPA_CHOICES).get(match.etapa_do_funil)
            })
        
        return Response({'status': 'already_final', 'etapa': match.etapa_do_funil})
    
    @action(detail=True, methods=['post'])
    def rejeitar(self, request, pk=None):
        """Rejeita um match (move para etapa 'rejeitado')."""
        match = self.get_object()
        match.etapa_do_funil = 'rejeitado'
        match.save()
        self._invalidate_stats_cache()
        
        return Response({'status': 'ok', 'codigo': match.codigo, 'etapa': 'rejeitado'})
    
    @action(detail=True, methods=['post'])
    def recuperar(self, request, pk=None):
        """Recupera um match rejeitado (volta para etapa 'novo')."""
        match = self.get_object()
        if match.etapa_do_funil != 'rejeitado':
            return Response(
                {'error': 'Apenas matches rejeitados podem ser recuperados'},
                status=status.HTTP_400_BAD_REQUEST
            )
        match.etapa_do_funil = 'novo'
        match.save()
        self._invalidate_stats_cache()
        
        return Response({'status': 'ok', 'codigo': match.codigo, 'etapa': 'novo'})
    
    @action(detail=False, methods=['post'])
    def backfill_bilateral(self, request):
        """
        Backfill existing matches: mark them as bilateral if they satisfy criteria.
        
        Criteria: the matched item (permuta_imovel/permuta_automovel/imovel_match) 
        must have at least one reverse interest registered.
        """
        from django.db.models import Exists, OuterRef
        
        has_reverse_permuta_imovel = Exists(
            InteressePermutaImovel.objects.filter(
                permuta_imovel=OuterRef('permuta_imovel')
            )
        )
        has_reverse_permuta_automovel = Exists(
            InteressePermutaAutomovel.objects.filter(
                permuta_automovel=OuterRef('permuta_automovel')
            )
        )
        has_reverse_imovel_match = Exists(
            InteresseImovel.objects.filter(
                imovel=OuterRef('imovel_match')
            )
        )
        
        matches_to_update = Match.objects.filter(is_bilateral=False).annotate(
            has_reverse_pi=has_reverse_permuta_imovel,
            has_reverse_pa=has_reverse_permuta_automovel,
            has_reverse_im=has_reverse_imovel_match
        )
        
        updated_count = 0
        for match in matches_to_update:
            should_be_bilateral = (
                (match.permuta_imovel_id and match.has_reverse_pi) or
                (match.permuta_automovel_id and match.has_reverse_pa) or
                (match.imovel_match_id and match.has_reverse_im)
            )
            if should_be_bilateral:
                match.is_bilateral = True
                match.save(update_fields=['is_bilateral'])
                updated_count += 1
        
        return Response({
            'status': 'success',
            'updated': updated_count,
            'message': f'{updated_count} matches marked as bilateral'
        })
