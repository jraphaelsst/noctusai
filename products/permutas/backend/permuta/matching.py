from django.db import IntegrityError
from django.apps import apps
from decimal import Decimal


def get_model(app_label, model_name):
    return apps.get_model(app_label, model_name)


def get_valor_minimo(interesse):
    """Retorna valor_minimo ou 0 se for None (wildcard para qualquer valor mínimo)"""
    return interesse.valor_minimo if interesse.valor_minimo is not None else Decimal('0')


def get_valor_maximo(interesse):
    """Retorna valor_maximo ou infinito se for None (wildcard para qualquer valor máximo)"""
    return interesse.valor_maximo if interesse.valor_maximo is not None else Decimal('999999999999')


def tipos_match(interesse_tipo, permuta_tipo):
    """
    Verifica se os tipos são compatíveis.
    Se qualquer um for None, considera como wildcard (match).
    Só rejeita se ambos estiverem definidos e forem diferentes.
    """
    if interesse_tipo is None or permuta_tipo is None:
        return True
    return interesse_tipo == permuta_tipo


def estados_match(interesse_estado, permuta_estado):
    """
    Verifica se os estados são compatíveis.
    Se qualquer um for None/vazio, considera como wildcard (match).
    """
    if not interesse_estado or not permuta_estado:
        return True
    return interesse_estado == permuta_estado


def zonas_match(interesse_zona, permuta_zona):
    """
    Verifica se as zonas são compatíveis.
    Se qualquer uma for None, considera como wildcard (match).
    """
    if interesse_zona is None or permuta_zona is None:
        return True
    return interesse_zona == permuta_zona


def valor_in_range(valor, valor_minimo, valor_maximo):
    """Verifica se o valor está dentro do range (inclusivo)"""
    if valor is None:
        return False
    return valor_minimo <= valor <= valor_maximo


def create_matches_for_interesse_imovel(interesse, user):
    Match = get_model('permuta', 'Match')
    PermutaImovel = get_model('permuta', 'PermutaImovel')
    Imovel = get_model('imovel', 'Imovel')
    from permuta.utils import generate_sequential_code
    
    created_count = 0
    
    valor_min = get_valor_minimo(interesse)
    valor_max = get_valor_maximo(interesse)
    
    permutas = PermutaImovel.objects.all()
    
    for permuta in permutas:
        if not valor_in_range(permuta.valor, valor_min, valor_max):
            continue
        if not tipos_match(interesse.tipo_imovel, permuta.tipo):
            continue
        if not estados_match(interesse.estado, permuta.estado):
            continue
        if not zonas_match(interesse.zona, permuta.zona):
            continue
        
        exists = Match.objects.filter(
            imovel=interesse.imovel,
            permuta_imovel=permuta
        ).exists()
        
        if not exists:
            try:
                codigo = generate_sequential_code('MT', Match)
                Match.objects.create(
                    codigo=codigo,
                    imovel=interesse.imovel,
                    permuta_imovel=permuta,
                    interesse_imovel=interesse,
                    etapa_do_funil='novo',
                    criado_por=user
                )
                created_count += 1
            except IntegrityError:
                pass
    
    imoveis = Imovel.objects.select_related('tipo', 'zona', 'condominio').exclude(id=interesse.imovel.id)
    
    for imovel_candidato in imoveis:
        if not valor_in_range(imovel_candidato.valor_venda, valor_min, valor_max):
            continue
        if not tipos_match(interesse.tipo_imovel, imovel_candidato.tipo):
            continue
        estado_imovel = imovel_candidato.condominio.estado if imovel_candidato.condominio else None
        if not estados_match(interesse.estado, estado_imovel):
            continue
        if not zonas_match(interesse.zona, imovel_candidato.zona):
            continue
        
        exists = Match.objects.filter(
            imovel=interesse.imovel,
            imovel_match=imovel_candidato
        ).exists()
        
        if not exists:
            try:
                codigo = generate_sequential_code('MT', Match)
                Match.objects.create(
                    codigo=codigo,
                    imovel=interesse.imovel,
                    imovel_match=imovel_candidato,
                    interesse_imovel=interesse,
                    etapa_do_funil='novo',
                    criado_por=user
                )
                created_count += 1
            except IntegrityError:
                pass
    
    return created_count


def create_matches_for_interesse_automovel(interesse, user):
    Match = get_model('permuta', 'Match')
    PermutaAutomovel = get_model('permuta', 'PermutaAutomovel')
    from permuta.utils import generate_sequential_code
    
    created_count = 0
    
    valor_min = get_valor_minimo(interesse)
    valor_max = get_valor_maximo(interesse)
    
    permutas = PermutaAutomovel.objects.all()
    
    for permuta in permutas:
        if not tipos_match(interesse.tipo_automovel, permuta.tipo):
            continue
        if not valor_in_range(permuta.valor, valor_min, valor_max):
            continue
        
        exists = Match.objects.filter(
            imovel=interesse.imovel,
            permuta_automovel=permuta
        ).exists()
        
        if not exists:
            try:
                codigo = generate_sequential_code('MT', Match)
                Match.objects.create(
                    codigo=codigo,
                    imovel=interesse.imovel,
                    permuta_automovel=permuta,
                    interesse_automovel=interesse,
                    etapa_do_funil='novo',
                    criado_por=user
                )
                created_count += 1
            except IntegrityError:
                pass
    
    return created_count


def create_matches_for_permuta_imovel(permuta, user):
    Match = get_model('permuta', 'Match')
    InteresseImovel = get_model('imovel', 'InteresseImovel')
    from permuta.utils import generate_sequential_code
    
    created_count = 0
    
    interesses = InteresseImovel.objects.select_related('imovel').all()
    
    for interesse in interesses:
        valor_min = get_valor_minimo(interesse)
        valor_max = get_valor_maximo(interesse)
        
        if not valor_in_range(permuta.valor, valor_min, valor_max):
            continue
        if not tipos_match(interesse.tipo_imovel, permuta.tipo):
            continue
        if not estados_match(interesse.estado, permuta.estado):
            continue
        if not zonas_match(interesse.zona, permuta.zona):
            continue
        
        exists = Match.objects.filter(
            imovel=interesse.imovel,
            permuta_imovel=permuta
        ).exists()
        
        if not exists:
            try:
                codigo = generate_sequential_code('MT', Match)
                Match.objects.create(
                    codigo=codigo,
                    imovel=interesse.imovel,
                    permuta_imovel=permuta,
                    interesse_imovel=interesse,
                    etapa_do_funil='novo',
                    criado_por=user
                )
                created_count += 1
            except IntegrityError:
                pass
    
    return created_count


def create_matches_for_permuta_automovel(permuta, user):
    Match = get_model('permuta', 'Match')
    InteresseAutomovel = get_model('imovel', 'InteresseAutomovel')
    from permuta.utils import generate_sequential_code
    
    created_count = 0
    
    interesses = InteresseAutomovel.objects.select_related('imovel').all()
    
    for interesse in interesses:
        valor_min = get_valor_minimo(interesse)
        valor_max = get_valor_maximo(interesse)
        
        if not tipos_match(interesse.tipo_automovel, permuta.tipo):
            continue
        if not valor_in_range(permuta.valor, valor_min, valor_max):
            continue
        
        exists = Match.objects.filter(
            imovel=interesse.imovel,
            permuta_automovel=permuta
        ).exists()
        
        if not exists:
            try:
                codigo = generate_sequential_code('MT', Match)
                Match.objects.create(
                    codigo=codigo,
                    imovel=interesse.imovel,
                    permuta_automovel=permuta,
                    interesse_automovel=interesse,
                    etapa_do_funil='novo',
                    criado_por=user
                )
                created_count += 1
            except IntegrityError:
                pass
    
    return created_count


def create_matches_for_imovel(imovel, user):
    """
    Quando um novo imóvel é criado ou atualizado, verifica se ele dá match
    com os interesses de outros imóveis.
    """
    Match = get_model('permuta', 'Match')
    InteresseImovel = get_model('imovel', 'InteresseImovel')
    from permuta.utils import generate_sequential_code
    
    created_count = 0
    
    if not imovel.valor_venda:
        return 0
    
    interesses = InteresseImovel.objects.select_related('imovel').exclude(imovel=imovel)
    
    for interesse in interesses:
        valor_min = get_valor_minimo(interesse)
        valor_max = get_valor_maximo(interesse)
        
        if not valor_in_range(imovel.valor_venda, valor_min, valor_max):
            continue
        
        if not tipos_match(interesse.tipo_imovel, imovel.tipo):
            continue
        
        estado_imovel = imovel.condominio.estado if imovel.condominio else None
        if not estados_match(interesse.estado, estado_imovel):
            continue
        
        if not zonas_match(interesse.zona, imovel.zona):
            continue
        
        exists = Match.objects.filter(
            imovel=interesse.imovel,
            imovel_match=imovel
        ).exists()
        
        if not exists:
            try:
                codigo = generate_sequential_code('MT', Match)
                Match.objects.create(
                    codigo=codigo,
                    imovel=interesse.imovel,
                    imovel_match=imovel,
                    interesse_imovel=interesse,
                    etapa_do_funil='novo',
                    criado_por=user
                )
                created_count += 1
            except IntegrityError:
                pass
    
    return created_count
