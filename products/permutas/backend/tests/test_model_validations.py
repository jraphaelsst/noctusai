import pytest
from django.core.exceptions import ValidationError
from tests.factories import (
    UserFactory, ImovelFactory, InteresseImovelFactory, InteresseAutomovelFactory,
    PermutaImovelFactory, PermutaAutomovelFactory, MatchFactory, TipoImovelFactory,
    ZonaFactory, CondominioFactory, ProprietarioFactory
)
from permuta.models import Match
from imovel.models import InteresseImovel, InteresseAutomovel


@pytest.mark.django_db
class TestMatchValidation:
    def test_match_requires_exactly_one_source(self):
        """Test that Match requires exactly one source."""
        user = UserFactory()
        imovel = ImovelFactory(criado_por=user)
        
        match = Match(
            imovel=imovel,
            criado_por=user,
            etapa_do_funil='novo'
        )
        with pytest.raises(ValidationError):
            match.clean()
    
    def test_match_with_permuta_imovel_source(self):
        """Test that Match with permuta_imovel source is valid."""
        user = UserFactory()
        imovel = ImovelFactory(criado_por=user)
        permuta = PermutaImovelFactory(criado_por=user)
        interesse = InteresseImovelFactory(imovel=imovel, criado_por=user)
        
        match = Match(
            imovel=imovel,
            permuta_imovel=permuta,
            interesse_imovel=interesse,
            criado_por=user,
            etapa_do_funil='novo',
            codigo='MT0001'
        )
        match.clean()
        match.save()
        
        assert match.pk is not None
    
    def test_match_with_permuta_automovel_source(self):
        """Test that Match with permuta_automovel source is valid."""
        user = UserFactory()
        imovel = ImovelFactory(criado_por=user)
        permuta = PermutaAutomovelFactory(criado_por=user)
        interesse = InteresseAutomovelFactory(imovel=imovel, criado_por=user)
        
        match = Match(
            imovel=imovel,
            permuta_automovel=permuta,
            interesse_automovel=interesse,
            criado_por=user,
            etapa_do_funil='novo',
            codigo='MT0002'
        )
        match.clean()
        match.save()
        
        assert match.pk is not None
    
    def test_match_with_imovel_match_source(self):
        """Test that Match with imovel_match source is valid."""
        user = UserFactory()
        imovel = ImovelFactory(criado_por=user)
        imovel_match = ImovelFactory(criado_por=user)
        interesse = InteresseImovelFactory(imovel=imovel, criado_por=user)
        
        match = Match(
            imovel=imovel,
            imovel_match=imovel_match,
            interesse_imovel=interesse,
            criado_por=user,
            etapa_do_funil='novo',
            codigo='MT0003'
        )
        match.clean()
        match.save()
        
        assert match.pk is not None


@pytest.mark.django_db
class TestInteresseValidation:
    def test_valor_minimo_must_be_less_than_maximo(self):
        """Test that valor_minimo <= valor_maximo."""
        user = UserFactory()
        imovel = ImovelFactory(criado_por=user)
        
        interesse = InteresseImovel(
            imovel=imovel,
            criado_por=user,
            valor_minimo=1000000,
            valor_maximo=500000
        )
        with pytest.raises(ValidationError):
            interesse.clean()
    
    def test_valid_valores(self):
        """Test that valid valor_minimo <= valor_maximo works."""
        user = UserFactory()
        imovel = ImovelFactory(criado_por=user)
        
        interesse = InteresseImovel(
            imovel=imovel,
            criado_por=user,
            valor_minimo=300000,
            valor_maximo=600000
        )
        interesse.clean()
        interesse.save()
        
        assert interesse.pk is not None
    
    def test_null_values_allowed(self):
        """Test that null values (wildcards) are allowed."""
        user = UserFactory()
        imovel = ImovelFactory(criado_por=user)
        
        interesse = InteresseImovel(
            imovel=imovel,
            criado_por=user,
            valor_minimo=None,
            valor_maximo=None
        )
        interesse.clean()
        interesse.save()
        
        assert interesse.pk is not None
    
    def test_interesse_automovel_validation(self):
        """Test InteresseAutomovel valor validation."""
        user = UserFactory()
        imovel = ImovelFactory(criado_por=user)
        
        interesse = InteresseAutomovel(
            imovel=imovel,
            criado_por=user,
            valor_minimo=500000,
            valor_maximo=100000
        )
        with pytest.raises(ValidationError):
            interesse.clean()


@pytest.mark.django_db
class TestCepValidation:
    def test_valid_cep_with_dash(self):
        """Test valid CEP format with dash."""
        user = UserFactory()
        condominio = CondominioFactory(criado_por=user, cep='12345-678')
        assert condominio.cep == '12345-678'
    
    def test_valid_cep_without_dash(self):
        """Test valid CEP format without dash."""
        user = UserFactory()
        condominio = CondominioFactory(criado_por=user, cep='12345678')
        assert condominio.cep == '12345678'


@pytest.mark.django_db
class TestPhoneValidation:
    def test_valid_phone_format(self):
        """Test valid phone formats."""
        user = UserFactory()
        proprietario = ProprietarioFactory(criado_por=user, telefone='11987654321')
        assert proprietario.telefone == '11987654321'
