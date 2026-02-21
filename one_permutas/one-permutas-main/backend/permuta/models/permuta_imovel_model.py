from django.db import models

from authsys.models import User


class PermutaImovel(models.Model):
    choices_tipo = (
        ('a', 'Apartamento'),
        ('c', 'Casa'),
        ('t', 'Terreno')
    )
    
    choices_zona = (
        ('n', 'Norte'),
        ('s', 'Sul'),
        ('l', 'Leste'),
        ('o', 'Oeste')
    )
    
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    proprietario = models.ForeignKey('proprietario.Proprietario', on_delete=models.DO_NOTHING)
    corretor = models.CharField(max_length=20)
    tipo = models.CharField(max_length=1, choices=choices_tipo)
    condominio = models.CharField(max_length=50)
    zona = models.CharField(max_length=1, choices=choices_zona)
    cep = models.CharField(max_length=20)
    estado = models.CharField(max_length=2)
    cidade = models.CharField(max_length=50)
    bairro = models.CharField(max_length=50)
    endereco = models.CharField(max_length=100)
    numero = models.PositiveIntegerField(blank=True, null=True)
    valor = models.PositiveIntegerField()
    
    def __str__(self):
        return self.tipo
