import pytest
from tests.factories import (
    UserFactory, ImovelFactory, InteresseImovelFactory, InteresseAutomovelFactory,
    PermutaImovelFactory, PermutaAutomovelFactory, TipoImovelFactory, 
    TipoAutomovelFactory, ZonaFactory, CondominioFactory
)
from permuta.matching import (
    tipos_match, valor_in_range, estados_match, zonas_match,
    get_valor_minimo, get_valor_maximo, create_matches_for_interesse_imovel,
    create_matches_for_interesse_automovel
)
from permuta.models import Match


@pytest.mark.django_db
class TestMatchingFunctions:
    def test_tipos_match_with_both_null(self):
        """Test that null tipos (wildcards) match."""
        assert tipos_match(None, None) is True
    
    def test_tipos_match_with_interesse_null(self):
        """Test that null interesse tipo matches any permuta tipo."""
        tipo = TipoImovelFactory()
        assert tipos_match(None, tipo) is True
    
    def test_tipos_match_with_permuta_null(self):
        """Test that any interesse tipo matches null permuta tipo."""
        tipo = TipoImovelFactory()
        assert tipos_match(tipo, None) is True
    
    def test_tipos_match_with_same_tipo(self):
        """Test that same tipos match."""
        tipo = TipoImovelFactory()
        assert tipos_match(tipo, tipo) is True
    
    def test_tipos_match_with_different_tipos(self):
        """Test that different tipos don't match."""
        tipo1 = TipoImovelFactory(nome='Apartamento')
        tipo2 = TipoImovelFactory(nome='Casa')
        assert tipos_match(tipo1, tipo2) is False
    
    def test_estados_match_with_both_empty(self):
        """Test that empty estados (wildcards) match."""
        assert estados_match('', '') is True
        assert estados_match(None, None) is True
    
    def test_estados_match_with_interesse_empty(self):
        """Test that empty interesse estado matches any permuta estado."""
        assert estados_match('', 'SP') is True
    
    def test_estados_match_with_same_estado(self):
        """Test that same estados match."""
        assert estados_match('SP', 'SP') is True
    
    def test_estados_match_with_different_estados(self):
        """Test that different estados don't match."""
        assert estados_match('SP', 'RJ') is False
    
    def test_zonas_match_with_both_null(self):
        """Test that null zonas (wildcards) match."""
        assert zonas_match(None, None) is True
    
    def test_zonas_match_with_interesse_null(self):
        """Test that null interesse zona matches any permuta zona."""
        zona = ZonaFactory()
        assert zonas_match(None, zona) is True
    
    def test_zonas_match_with_same_zona(self):
        """Test that same zonas match."""
        zona = ZonaFactory()
        assert zonas_match(zona, zona) is True
    
    def test_zonas_match_with_different_zonas(self):
        """Test that different zonas don't match."""
        zona1 = ZonaFactory(nome='Norte')
        zona2 = ZonaFactory(nome='Sul')
        assert zonas_match(zona1, zona2) is False
    
    def test_valor_in_range_within_range(self):
        """Test value within range returns True."""
        assert valor_in_range(500000, 300000, 700000) is True
    
    def test_valor_in_range_below_minimum(self):
        """Test value below minimum returns False."""
        assert valor_in_range(200000, 300000, 700000) is False
    
    def test_valor_in_range_above_maximum(self):
        """Test value above maximum returns False."""
        assert valor_in_range(800000, 300000, 700000) is False
    
    def test_valor_in_range_at_boundary(self):
        """Test value at boundary returns True."""
        assert valor_in_range(300000, 300000, 700000) is True
        assert valor_in_range(700000, 300000, 700000) is True
    
    def test_valor_in_range_with_none_value(self):
        """Test None value returns False."""
        assert valor_in_range(None, 300000, 700000) is False


@pytest.mark.django_db
class TestWildcardMatching:
    def test_get_valor_minimo_returns_zero_for_none(self):
        """Test that None valor_minimo returns 0."""
        interesse = InteresseImovelFactory(valor_minimo=None)
        assert get_valor_minimo(interesse) == 0
    
    def test_get_valor_minimo_returns_value(self):
        """Test that set valor_minimo is returned."""
        interesse = InteresseImovelFactory(valor_minimo=300000, valor_maximo=600000)
        assert get_valor_minimo(interesse) == 300000
    
    def test_get_valor_maximo_returns_infinity_for_none(self):
        """Test that None valor_maximo returns very large number."""
        interesse = InteresseImovelFactory(valor_maximo=None)
        assert get_valor_maximo(interesse) > 999999999
    
    def test_get_valor_maximo_returns_value(self):
        """Test that set valor_maximo is returned."""
        interesse = InteresseImovelFactory(valor_minimo=300000, valor_maximo=600000)
        assert get_valor_maximo(interesse) == 600000


@pytest.mark.django_db
class TestMatchCreation:
    def test_create_matches_for_interesse_imovel(self):
        """Test that matches are created for interesse imovel."""
        user = UserFactory()
        tipo = TipoImovelFactory()
        zona = ZonaFactory()
        
        imovel = ImovelFactory(criado_por=user, tipo=tipo, zona=zona)
        
        permuta = PermutaImovelFactory(
            criado_por=user,
            tipo=tipo,
            zona=zona,
            estado='SP',
            valor=500000
        )
        
        interesse = InteresseImovelFactory(
            imovel=imovel,
            criado_por=user,
            tipo_imovel=tipo,
            zona=zona,
            estado='SP',
            valor_minimo=300000,
            valor_maximo=700000
        )
        
        created_count = create_matches_for_interesse_imovel(interesse, user)
        
        assert created_count >= 1
        assert Match.objects.filter(imovel=imovel, permuta_imovel=permuta).exists()
    
    def test_create_matches_for_interesse_automovel(self):
        """Test that matches are created for interesse automovel."""
        user = UserFactory()
        tipo = TipoAutomovelFactory()
        
        imovel = ImovelFactory(criado_por=user)
        
        permuta = PermutaAutomovelFactory(
            criado_por=user,
            tipo=tipo,
            valor=150000
        )
        
        interesse = InteresseAutomovelFactory(
            imovel=imovel,
            criado_por=user,
            tipo_automovel=tipo,
            valor_minimo=100000,
            valor_maximo=200000
        )
        
        created_count = create_matches_for_interesse_automovel(interesse, user)
        
        assert created_count >= 1
        assert Match.objects.filter(imovel=imovel, permuta_automovel=permuta).exists()
    
    def test_wildcard_tipo_creates_match(self):
        """Test that wildcard tipo (None) creates matches with any tipo."""
        user = UserFactory()
        tipo = TipoImovelFactory()
        
        imovel = ImovelFactory(criado_por=user)
        
        permuta = PermutaImovelFactory(
            criado_por=user,
            tipo=tipo,
            estado='SP',
            valor=500000
        )
        
        interesse = InteresseImovelFactory(
            imovel=imovel,
            criado_por=user,
            tipo_imovel=None,
            zona=None,
            estado='SP',
            valor_minimo=300000,
            valor_maximo=700000
        )
        
        created_count = create_matches_for_interesse_imovel(interesse, user)
        
        assert created_count >= 1
