"""
Bilateral Matching Service

This module implements BILATERAL matching logic where matches are created ONLY when:
1. Property A has an interest that is compatible with Permuta/Property B
2. Permuta/Property B has an REVERSE interest that is compatible with Property A

Both sides must have interests registered and be mutually compatible.

OPTIMIZATION: Filtering is done at the DB level using Django Q objects,
avoiding O(n²) in-Python loops. Wildcard logic (None = match any) is
preserved via Q(field=value) | Q(field__isnull=True) patterns.
"""
from django.db import IntegrityError
from django.db.models import Q
from django.apps import apps
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def get_model(app_label, model_name):
    return apps.get_model(app_label, model_name)


def get_valor_minimo(interesse):
    """Return valor_minimo or 0 if None (wildcard for any minimum value)"""
    return interesse.valor_minimo if interesse.valor_minimo is not None else Decimal('0')


def get_valor_maximo(interesse):
    """Return valor_maximo or infinity if None (wildcard for any maximum value)"""
    return interesse.valor_maximo if interesse.valor_maximo is not None else Decimal('999999999999')


def tipos_match(interesse_tipo, target_tipo):
    """
    Check if types are compatible.
    If either is None, consider it a wildcard (match).
    Only reject if both are defined and different.
    """
    if interesse_tipo is None or target_tipo is None:
        return True
    return interesse_tipo == target_tipo


def estados_match(interesse_estado, target_estado):
    """
    Check if estados are compatible.
    If either is None/empty, consider it a wildcard (match).
    """
    if not interesse_estado or not target_estado:
        return True
    return interesse_estado == target_estado


def zonas_match(interesse_zona, target_zona):
    """
    Check if zonas are compatible.
    If either is None, consider it a wildcard (match).
    """
    if interesse_zona is None or target_zona is None:
        return True
    return interesse_zona == target_zona


def valor_in_range(valor, valor_minimo, valor_maximo):
    """Check if valor is within range (inclusive)"""
    if valor is None:
        return False
    return valor_minimo <= valor <= valor_maximo


# ─── DB-level filter builders ───────────────────────────────────────────────


def _build_permuta_imovel_filter(interesse):
    """
    Build a Q filter for PermutaImovel candidates that could match an InteresseImovel.
    Handles wildcard logic: None tipo/zona on the interesse means 'accept any'.
    """
    q = Q()
    valor_min = get_valor_minimo(interesse)
    valor_max = get_valor_maximo(interesse)
    q &= Q(valor__gte=valor_min, valor__lte=valor_max)

    if interesse.tipo_imovel is not None:
        q &= Q(tipo=interesse.tipo_imovel) | Q(tipo__isnull=True)
    if interesse.zona is not None:
        q &= Q(zona=interesse.zona) | Q(zona__isnull=True)
    if interesse.estado:
        q &= Q(estado=interesse.estado) | Q(estado='')
    return q


def _build_imovel_filter_from_interesse_imovel(interesse):
    """
    Build a Q filter for Imovel candidates that could match an InteresseImovel.
    Used for imovel-to-imovel matching.
    """
    q = Q()
    valor_min = get_valor_minimo(interesse)
    valor_max = get_valor_maximo(interesse)
    q &= Q(valor_venda__gte=valor_min, valor_venda__lte=valor_max)

    if interesse.tipo_imovel is not None:
        q &= Q(tipo=interesse.tipo_imovel) | Q(tipo__isnull=True)
    if interesse.zona is not None:
        q &= Q(zona=interesse.zona) | Q(zona__isnull=True)
    if interesse.estado:
        q &= Q(condominio__estado=interesse.estado) | Q(condominio__estado='')
    return q


def _build_permuta_automovel_filter(interesse):
    """
    Build a Q filter for PermutaAutomovel candidates that could match an InteresseAutomovel.
    """
    q = Q()
    valor_min = get_valor_minimo(interesse)
    valor_max = get_valor_maximo(interesse)
    q &= Q(valor__gte=valor_min, valor__lte=valor_max)

    if interesse.tipo_automovel is not None:
        q &= Q(tipo=interesse.tipo_automovel) | Q(tipo__isnull=True)
    return q


def _build_interesse_imovel_filter_for_permuta(permuta):
    """
    Build a Q filter for InteresseImovel records whose criteria could match a PermutaImovel.
    The interest's tipo_imovel/zona must match the permuta's tipo/zona (or be None = wildcard).
    The permuta's valor must fall within the interest's [valor_minimo, valor_maximo] range.
    """
    q = Q()
    # Interest tipo_imovel must match permuta.tipo OR be None (wildcard)
    if permuta.tipo is not None:
        q &= Q(tipo_imovel=permuta.tipo) | Q(tipo_imovel__isnull=True)
    if permuta.zona is not None:
        q &= Q(zona=permuta.zona) | Q(zona__isnull=True)
    if permuta.estado:
        q &= Q(estado=permuta.estado) | Q(estado='')
    # The permuta's valor must fall within the interest's range
    q &= (Q(valor_minimo__lte=permuta.valor) | Q(valor_minimo__isnull=True))
    q &= (Q(valor_maximo__gte=permuta.valor) | Q(valor_maximo__isnull=True))
    return q


def _build_interesse_imovel_filter_for_imovel(imovel):
    """
    Build a Q filter for InteresseImovel records whose criteria could match an Imovel.
    Used to find other imóveis' interests that could want THIS imovel.
    """
    q = Q()
    if imovel.tipo is not None:
        q &= Q(tipo_imovel=imovel.tipo) | Q(tipo_imovel__isnull=True)
    if imovel.zona is not None:
        q &= Q(zona=imovel.zona) | Q(zona__isnull=True)
    estado_imovel = imovel.condominio.estado if imovel.condominio else None
    if estado_imovel:
        q &= Q(estado=estado_imovel) | Q(estado='')
    q &= (Q(valor_minimo__lte=imovel.valor_venda) | Q(valor_minimo__isnull=True))
    q &= (Q(valor_maximo__gte=imovel.valor_venda) | Q(valor_maximo__isnull=True))
    return q


def _build_interesse_automovel_filter_for_permuta(permuta):
    """
    Build a Q filter for InteresseAutomovel records whose criteria could match a PermutaAutomovel.
    """
    q = Q()
    if permuta.tipo is not None:
        q &= Q(tipo_automovel=permuta.tipo) | Q(tipo_automovel__isnull=True)
    q &= (Q(valor_minimo__lte=permuta.valor) | Q(valor_minimo__isnull=True))
    q &= (Q(valor_maximo__gte=permuta.valor) | Q(valor_maximo__isnull=True))
    return q


# ─── In-Python compatibility checks (kept for reverse-side verification) ────


def interesse_imovel_matches_permuta_imovel(interesse_a, permuta_b):
    """
    Check if InteresseImovel from Property A matches PermutaImovel B.
    Returns True if A wants what B offers.
    """
    valor_min = get_valor_minimo(interesse_a)
    valor_max = get_valor_maximo(interesse_a)

    if not valor_in_range(permuta_b.valor, valor_min, valor_max):
        return False
    if not tipos_match(interesse_a.tipo_imovel, permuta_b.tipo):
        return False
    if not estados_match(interesse_a.estado, permuta_b.estado):
        return False
    if not zonas_match(interesse_a.zona, permuta_b.zona):
        return False

    return True


def interesse_permuta_imovel_matches_imovel(interesse_permuta_b, imovel_a):
    """
    Check if InteressePermutaImovel from PermutaImovel B matches Imovel A.
    Returns True if B's owner wants what A offers.
    """
    valor_min = get_valor_minimo(interesse_permuta_b)
    valor_max = get_valor_maximo(interesse_permuta_b)

    if not valor_in_range(imovel_a.valor_venda, valor_min, valor_max):
        return False
    if not tipos_match(interesse_permuta_b.tipo_imovel, imovel_a.tipo):
        return False

    estado_imovel = imovel_a.condominio.estado if imovel_a.condominio else None
    if not estados_match(interesse_permuta_b.estado, estado_imovel):
        return False
    if not zonas_match(interesse_permuta_b.zona, imovel_a.zona):
        return False

    return True


def interesse_automovel_matches_permuta_automovel(interesse_a, permuta_b):
    """
    Check if InteresseAutomovel from Property A matches PermutaAutomovel B.
    Returns True if A wants what B offers.
    """
    valor_min = get_valor_minimo(interesse_a)
    valor_max = get_valor_maximo(interesse_a)

    if not tipos_match(interesse_a.tipo_automovel, permuta_b.tipo):
        return False
    if not valor_in_range(permuta_b.valor, valor_min, valor_max):
        return False

    return True


def interesse_permuta_automovel_matches_imovel(interesse_permuta_b, imovel_a):
    """
    Check if InteressePermutaAutomovel from PermutaAutomovel B matches Imovel A.
    Returns True if B's owner wants what A offers (property).
    """
    valor_min = get_valor_minimo(interesse_permuta_b)
    valor_max = get_valor_maximo(interesse_permuta_b)

    if not valor_in_range(imovel_a.valor_venda, valor_min, valor_max):
        return False
    if not tipos_match(interesse_permuta_b.tipo_imovel, imovel_a.tipo):
        return False

    estado_imovel = imovel_a.condominio.estado if imovel_a.condominio else None
    if not estados_match(interesse_permuta_b.estado, estado_imovel):
        return False
    if not zonas_match(interesse_permuta_b.zona, imovel_a.zona):
        return False

    return True


def interesse_imovel_matches_imovel(interesse_a, imovel_b):
    """
    Check if InteresseImovel from Property A matches Imovel B.
    Returns True if A wants what B offers.
    """
    valor_min = get_valor_minimo(interesse_a)
    valor_max = get_valor_maximo(interesse_a)

    if not valor_in_range(imovel_b.valor_venda, valor_min, valor_max):
        return False
    if not tipos_match(interesse_a.tipo_imovel, imovel_b.tipo):
        return False

    estado_imovel = imovel_b.condominio.estado if imovel_b.condominio else None
    if not estados_match(interesse_a.estado, estado_imovel):
        return False
    if not zonas_match(interesse_a.zona, imovel_b.zona):
        return False

    return True


# ─── Match creation helpers ─────────────────────────────────────────────────


def create_bilateral_match_imovel_permuta(imovel_a, interesse_a, permuta_b, interesse_b, user):
    """
    Create a bilateral match between Imovel A and PermutaImovel B.
    Both sides have verified compatible interests.
    """
    Match = get_model('permuta', 'Match')
    from permuta.utils import generate_sequential_code

    exists = Match.objects.filter(
        imovel=imovel_a,
        permuta_imovel=permuta_b
    ).exists()

    if exists:
        return 0

    try:
        codigo = generate_sequential_code('MT', Match)
        Match.objects.create(
            codigo=codigo,
            imovel=imovel_a,
            permuta_imovel=permuta_b,
            interesse_imovel=interesse_a,
            etapa_do_funil='novo',
            is_bilateral=True,
            criado_por=user
        )
        logger.info(f"Bilateral match created: {imovel_a.ref} <-> {permuta_b.codigo}")
        return 1
    except IntegrityError:
        return 0


def create_bilateral_match_imovel_automovel(imovel_a, interesse_a, permuta_b, interesse_b, user):
    """
    Create a bilateral match between Imovel A and PermutaAutomovel B.
    Both sides have verified compatible interests.
    """
    Match = get_model('permuta', 'Match')
    from permuta.utils import generate_sequential_code

    exists = Match.objects.filter(
        imovel=imovel_a,
        permuta_automovel=permuta_b
    ).exists()

    if exists:
        return 0

    try:
        codigo = generate_sequential_code('MT', Match)
        Match.objects.create(
            codigo=codigo,
            imovel=imovel_a,
            permuta_automovel=permuta_b,
            interesse_automovel=interesse_a,
            etapa_do_funil='novo',
            is_bilateral=True,
            criado_por=user
        )
        logger.info(f"Bilateral match created: {imovel_a.ref} <-> {permuta_b.codigo}")
        return 1
    except IntegrityError:
        return 0


def create_bilateral_match_imovel_imovel(imovel_a, interesse_a, imovel_b, interesse_b, user):
    """
    Create a bilateral match between Imovel A and Imovel B.
    Both sides have verified compatible interests.
    """
    Match = get_model('permuta', 'Match')
    from permuta.utils import generate_sequential_code

    exists = Match.objects.filter(
        imovel=imovel_a,
        imovel_match=imovel_b
    ).exists()

    if exists:
        return 0

    try:
        codigo = generate_sequential_code('MT', Match)
        Match.objects.create(
            codigo=codigo,
            imovel=imovel_a,
            imovel_match=imovel_b,
            interesse_imovel=interesse_a,
            etapa_do_funil='novo',
            is_bilateral=True,
            criado_por=user
        )
        logger.info(f"Bilateral match created: {imovel_a.ref} <-> {imovel_b.ref}")
        return 1
    except IntegrityError:
        return 0


# ─── Optimized matching functions (DB-level filtering) ──────────────────────


def create_bilateral_matches_for_interesse_imovel(interesse, user):
    """
    BILATERAL matching: Find matches for InteresseImovel.
    Creates matches only when BOTH sides are compatible.

    Scenario: Imovel A (with interesse) wants PermutaImovel B or Imovel B
    - For PermutaImovel: B must have InteressePermutaImovel that wants A
    - For Imovel: B must have InteresseImovel that wants A

    OPTIMIZED: Uses DB-level filters to narrow candidates before Python checks.
    """
    InteressePermutaImovel = get_model('permuta', 'InteressePermutaImovel')
    InteresseImovel = get_model('imovel', 'InteresseImovel')
    PermutaImovel = get_model('permuta', 'PermutaImovel')
    Imovel = get_model('imovel', 'Imovel')

    imovel_a = interesse.imovel
    created_count = 0

    # --- PermutaImovel candidates (DB-filtered) ---
    perm_filter = _build_permuta_imovel_filter(interesse)
    permutas = PermutaImovel.objects.filter(perm_filter).prefetch_related('interesses_permuta')

    for permuta_b in permutas:
        for interesse_permuta_b in permuta_b.interesses_permuta.all():
            if interesse_permuta_imovel_matches_imovel(interesse_permuta_b, imovel_a):
                created_count += create_bilateral_match_imovel_permuta(
                    imovel_a, interesse, permuta_b, interesse_permuta_b, user
                )
                break

    # --- Imovel-to-Imovel candidates (DB-filtered) ---
    imovel_filter = _build_imovel_filter_from_interesse_imovel(interesse)
    imoveis_b = Imovel.objects.filter(imovel_filter).select_related(
        'tipo', 'zona', 'condominio'
    ).exclude(id=imovel_a.id)

    for imovel_b in imoveis_b:
        interesses_b = InteresseImovel.objects.filter(imovel=imovel_b)
        for interesse_b in interesses_b:
            if interesse_imovel_matches_imovel(interesse_b, imovel_a):
                created_count += create_bilateral_match_imovel_imovel(
                    imovel_a, interesse, imovel_b, interesse_b, user
                )
                break

    return created_count


def create_bilateral_matches_for_interesse_automovel(interesse, user):
    """
    BILATERAL matching: Find matches for InteresseAutomovel.
    Creates matches only when BOTH sides are compatible.

    Scenario: Imovel A (with interesse) wants PermutaAutomovel B
    - B must have InteressePermutaAutomovel that wants A (property)

    OPTIMIZED: Uses DB-level filters to narrow candidates before Python checks.
    """
    PermutaAutomovel = get_model('permuta', 'PermutaAutomovel')

    imovel_a = interesse.imovel
    created_count = 0

    auto_filter = _build_permuta_automovel_filter(interesse)
    permutas = PermutaAutomovel.objects.filter(auto_filter).prefetch_related('interesses_permuta')

    for permuta_b in permutas:
        for interesse_permuta_b in permuta_b.interesses_permuta.all():
            if interesse_permuta_automovel_matches_imovel(interesse_permuta_b, imovel_a):
                created_count += create_bilateral_match_imovel_automovel(
                    imovel_a, interesse, permuta_b, interesse_permuta_b, user
                )
                break

    return created_count


def create_bilateral_matches_for_permuta_imovel(permuta, user):
    """
    BILATERAL matching: Find matches when a PermutaImovel is created/updated.
    Creates matches only when BOTH sides are compatible.

    Scenario: PermutaImovel B (with interesse) can match with Imovel A
    - A must have InteresseImovel that wants B
    - B must have InteressePermutaImovel that wants A

    OPTIMIZED: Uses DB-level filters to narrow InteresseImovel candidates.
    """
    InteressePermutaImovel = get_model('permuta', 'InteressePermutaImovel')
    InteresseImovel = get_model('imovel', 'InteresseImovel')

    created_count = 0

    interesses_permuta = InteressePermutaImovel.objects.filter(permuta_imovel=permuta)
    if not interesses_permuta.exists():
        return 0

    # DB-filtered: only interests whose criteria could match this permuta
    interesse_filter = _build_interesse_imovel_filter_for_permuta(permuta)
    interesses_a = InteresseImovel.objects.filter(interesse_filter).select_related(
        'imovel', 'imovel__tipo', 'imovel__zona', 'imovel__condominio'
    )

    for interesse_a in interesses_a:
        imovel_a = interesse_a.imovel

        for interesse_permuta_b in interesses_permuta:
            if interesse_permuta_imovel_matches_imovel(interesse_permuta_b, imovel_a):
                created_count += create_bilateral_match_imovel_permuta(
                    imovel_a, interesse_a, permuta, interesse_permuta_b, user
                )
                break

    return created_count


def create_bilateral_matches_for_permuta_automovel(permuta, user):
    """
    BILATERAL matching: Find matches when a PermutaAutomovel is created/updated.
    Creates matches only when BOTH sides are compatible.

    Scenario: PermutaAutomovel B (with interesse) can match with Imovel A
    - A must have InteresseAutomovel that wants B
    - B must have InteressePermutaAutomovel that wants A

    OPTIMIZED: Uses DB-level filters to narrow InteresseAutomovel candidates.
    """
    InteressePermutaAutomovel = get_model('permuta', 'InteressePermutaAutomovel')
    InteresseAutomovel = get_model('imovel', 'InteresseAutomovel')

    created_count = 0

    interesses_permuta = InteressePermutaAutomovel.objects.filter(permuta_automovel=permuta)
    if not interesses_permuta.exists():
        return 0

    # DB-filtered: only interests whose criteria could match this permuta
    auto_filter = _build_interesse_automovel_filter_for_permuta(permuta)
    interesses_a = InteresseAutomovel.objects.filter(auto_filter).select_related(
        'imovel', 'imovel__tipo', 'imovel__zona', 'imovel__condominio'
    )

    for interesse_a in interesses_a:
        imovel_a = interesse_a.imovel

        for interesse_permuta_b in interesses_permuta:
            if interesse_permuta_automovel_matches_imovel(interesse_permuta_b, imovel_a):
                created_count += create_bilateral_match_imovel_automovel(
                    imovel_a, interesse_a, permuta, interesse_permuta_b, user
                )
                break

    return created_count


def create_bilateral_matches_for_interesse_permuta_imovel(interesse_permuta, user):
    """
    BILATERAL matching: When InteressePermutaImovel is added to PermutaImovel B.
    Finds all Imoveis that want B AND that B now wants in return.

    OPTIMIZED: Uses DB-level filters to narrow InteresseImovel candidates.
    """
    InteresseImovel = get_model('imovel', 'InteresseImovel')

    permuta_b = interesse_permuta.permuta_imovel
    created_count = 0

    # DB-filtered: only interests whose criteria could match this permuta
    interesse_filter = _build_interesse_imovel_filter_for_permuta(permuta_b)
    interesses_a = InteresseImovel.objects.filter(interesse_filter).select_related(
        'imovel', 'imovel__tipo', 'imovel__zona', 'imovel__condominio'
    )

    for interesse_a in interesses_a:
        imovel_a = interesse_a.imovel

        if interesse_permuta_imovel_matches_imovel(interesse_permuta, imovel_a):
            created_count += create_bilateral_match_imovel_permuta(
                imovel_a, interesse_a, permuta_b, interesse_permuta, user
            )

    return created_count


def create_bilateral_matches_for_interesse_permuta_automovel(interesse_permuta, user):
    """
    BILATERAL matching: When InteressePermutaAutomovel is added to PermutaAutomovel B.
    Finds all Imoveis that want B AND that B now wants in return.

    OPTIMIZED: Uses DB-level filters to narrow InteresseAutomovel candidates.
    """
    InteresseAutomovel = get_model('imovel', 'InteresseAutomovel')

    permuta_b = interesse_permuta.permuta_automovel
    created_count = 0

    # DB-filtered: only interests whose criteria could match this permuta
    auto_filter = _build_interesse_automovel_filter_for_permuta(permuta_b)
    interesses_a = InteresseAutomovel.objects.filter(auto_filter).select_related(
        'imovel', 'imovel__tipo', 'imovel__zona', 'imovel__condominio'
    )

    for interesse_a in interesses_a:
        imovel_a = interesse_a.imovel

        if interesse_permuta_automovel_matches_imovel(interesse_permuta, imovel_a):
            created_count += create_bilateral_match_imovel_automovel(
                imovel_a, interesse_a, permuta_b, interesse_permuta, user
            )

    return created_count


def create_bilateral_matches_for_imovel(imovel, user):
    """
    BILATERAL matching: When Imovel is created/updated.
    Check if this imovel can now match with any existing interests.

    This happens when:
    - Imovel A has interests that might match permutas
    - OR when Imovel A becomes a target for other imoveis' interests

    OPTIMIZED: Uses DB-level filters instead of iterating all records.
    """
    InteresseImovel = get_model('imovel', 'InteresseImovel')

    created_count = 0

    # Match imovel A's interests against permutas/other imoveis
    interesses_a = InteresseImovel.objects.filter(imovel=imovel)
    for interesse in interesses_a:
        created_count += create_bilateral_matches_for_interesse_imovel(interesse, user)

    InteresseAutomovel = get_model('imovel', 'InteresseAutomovel')
    interesses_automovel = InteresseAutomovel.objects.filter(imovel=imovel)
    for interesse in interesses_automovel:
        created_count += create_bilateral_matches_for_interesse_automovel(interesse, user)

    # Check if OTHER imoveis' interests now match THIS imovel (reverse direction)
    # DB-filtered: only interests that could want this imovel
    reverse_filter = _build_interesse_imovel_filter_for_imovel(imovel)
    other_interesses = InteresseImovel.objects.filter(reverse_filter).select_related(
        'imovel', 'imovel__tipo', 'imovel__zona', 'imovel__condominio'
    ).exclude(imovel=imovel)

    my_interesses = InteresseImovel.objects.filter(imovel=imovel)

    for other_interesse in other_interesses:
        other_imovel = other_interesse.imovel

        for my_interesse in my_interesses:
            if interesse_imovel_matches_imovel(my_interesse, other_imovel):
                created_count += create_bilateral_match_imovel_imovel(
                    other_imovel, other_interesse, imovel, my_interesse, user
                )
                break

    return created_count
