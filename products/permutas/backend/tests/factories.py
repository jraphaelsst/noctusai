import factory
from factory.django import DjangoModelFactory
from faker import Faker
from django.contrib.auth import get_user_model

User = get_user_model()
fake = Faker('pt_BR')


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f'user{n}')
    email = factory.LazyAttribute(lambda obj: f'{obj.username}@example.com')
    password = factory.PostGenerationMethodCall('set_password', 'testpass123')


class TipoImovelFactory(DjangoModelFactory):
    class Meta:
        model = 'tipo_imovel.TipoImovel'
        skip_postgeneration_save = True
    
    criado_por = factory.SubFactory(UserFactory)
    nome = factory.Sequence(lambda n: f'Tipo Imóvel {n}')


class TipoAutomovelFactory(DjangoModelFactory):
    class Meta:
        model = 'tipo_automovel.TipoAutomovel'
        skip_postgeneration_save = True
    
    criado_por = factory.SubFactory(UserFactory)
    nome = factory.Sequence(lambda n: f'Tipo Automóvel {n}')


class ZonaFactory(DjangoModelFactory):
    class Meta:
        model = 'zona.Zona'
        skip_postgeneration_save = True
    
    criado_por = factory.SubFactory(UserFactory)
    nome = factory.Sequence(lambda n: f'Zona {n}')
    descricao = factory.Faker('text', max_nb_chars=200, locale='pt_BR')


class CorretorFactory(DjangoModelFactory):
    class Meta:
        model = 'corretor.Corretor'
        skip_postgeneration_save = True
    
    criado_por = factory.SubFactory(UserFactory)
    nome = factory.Faker('name', locale='pt_BR')
    telefone = '11987654321'
    email = factory.Faker('email')
    creci = factory.Sequence(lambda n: f'CRECI-{n:05d}')


class ProprietarioFactory(DjangoModelFactory):
    class Meta:
        model = 'proprietario.Proprietario'
        skip_postgeneration_save = True
    
    criado_por = factory.SubFactory(UserFactory)
    corretor = factory.SubFactory(CorretorFactory)
    nome = factory.Faker('name', locale='pt_BR')
    telefone = '11987654321'
    email = factory.Faker('email')


class CondominioFactory(DjangoModelFactory):
    class Meta:
        model = 'condominio.Condominio'
        skip_postgeneration_save = True
    
    criado_por = factory.SubFactory(UserFactory)
    nome = factory.Faker('company', locale='pt_BR')
    cep = '12345-678'
    estado = 'SP'
    cidade = 'São Paulo'
    bairro = 'Centro'
    endereco = factory.Faker('street_name', locale='pt_BR')
    numero = factory.Faker('random_int', min=1, max=1000)
    km = factory.Faker('random_int', min=1, max=50)
    valor_condominio = factory.Faker('random_int', min=300, max=2000)


class ImovelFactory(DjangoModelFactory):
    class Meta:
        model = 'imovel.Imovel'
        skip_postgeneration_save = True
    
    criado_por = factory.SubFactory(UserFactory)
    corretor = factory.SubFactory(CorretorFactory)
    proprietario = factory.SubFactory(ProprietarioFactory)
    condominio = factory.SubFactory(CondominioFactory)
    tipo = factory.SubFactory(TipoImovelFactory)
    zona = factory.SubFactory(ZonaFactory)
    ref = factory.Sequence(lambda n: f'IM{n:05d}')
    valor_venda = factory.Faker('random_int', min=200000, max=2000000)


class InteresseImovelFactory(DjangoModelFactory):
    class Meta:
        model = 'imovel.InteresseImovel'
        skip_postgeneration_save = True
    
    imovel = factory.SubFactory(ImovelFactory)
    criado_por = factory.SubFactory(UserFactory)
    tipo_imovel = factory.SubFactory(TipoImovelFactory)
    zona = factory.SubFactory(ZonaFactory)
    valor_minimo = factory.Faker('random_int', min=100000, max=500000)
    valor_maximo = factory.Faker('random_int', min=600000, max=1500000)


class InteresseAutomovelFactory(DjangoModelFactory):
    class Meta:
        model = 'imovel.InteresseAutomovel'
        skip_postgeneration_save = True
    
    imovel = factory.SubFactory(ImovelFactory)
    criado_por = factory.SubFactory(UserFactory)
    tipo_automovel = factory.SubFactory(TipoAutomovelFactory)
    valor_minimo = factory.Faker('random_int', min=50000, max=200000)
    valor_maximo = factory.Faker('random_int', min=250000, max=500000)


class PermutaImovelFactory(DjangoModelFactory):
    class Meta:
        model = 'permuta.PermutaImovel'
        skip_postgeneration_save = True
    
    codigo = factory.Sequence(lambda n: f'PI{n:04d}')
    criado_por = factory.SubFactory(UserFactory)
    proprietario = factory.SubFactory(ProprietarioFactory)
    corretor = factory.SubFactory(CorretorFactory)
    tipo = factory.SubFactory(TipoImovelFactory)
    zona = factory.SubFactory(ZonaFactory)
    condominio = 'Condomínio Teste'
    cep = '12345-678'
    estado = 'SP'
    cidade = 'São Paulo'
    bairro = 'Centro'
    endereco = 'Rua Teste'
    numero = 100
    valor = factory.Faker('random_int', min=200000, max=1500000)


class PermutaAutomovelFactory(DjangoModelFactory):
    class Meta:
        model = 'permuta.PermutaAutomovel'
        skip_postgeneration_save = True
    
    codigo = factory.Sequence(lambda n: f'PA{n:04d}')
    criado_por = factory.SubFactory(UserFactory)
    proprietario = factory.SubFactory(ProprietarioFactory)
    corretor = factory.SubFactory(CorretorFactory)
    tipo = factory.SubFactory(TipoAutomovelFactory)
    marca = 'Toyota'
    modelo = 'Corolla'
    motor = 'f'
    valor = factory.Faker('random_int', min=50000, max=300000)


class MatchFactory(DjangoModelFactory):
    class Meta:
        model = 'permuta.Match'
        skip_postgeneration_save = True
    
    codigo = factory.Sequence(lambda n: f'MT{n:04d}')
    imovel = factory.SubFactory(ImovelFactory)
    permuta_imovel = factory.SubFactory(PermutaImovelFactory)
    interesse_imovel = factory.SubFactory(InteresseImovelFactory)
    etapa_do_funil = 'novo'
    ordem = 0
    criado_por = factory.SubFactory(UserFactory)
