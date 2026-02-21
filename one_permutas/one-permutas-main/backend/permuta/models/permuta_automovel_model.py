from django.db import models

from authsys.models import User


class PermutaAutomovel(models.Model):
    choices_tipo = (
        ('c', 'Carro'),
        ('m', 'Moto'),
        ('s', 'SUV')
        )
    
    choices_motor = (
        ('g', 'Gasolina'),
        ('a', 'Álcool'),
        ('f', 'Flex'),
        ('e', 'Elétrico'),
        ('h', 'Híbrido')
    )
    
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    proprietario = models.ForeignKey('proprietario.Proprietario', on_delete=models.DO_NOTHING)
    corretor = models.CharField(max_length=20)
    tipo = models.CharField(max_length=1, choices=choices_tipo)
    marca = models.CharField(max_length=20)
    modelo = models.CharField(max_length=20)
    motor = models.CharField(max_length=1, choices=choices_motor, blank=True, null=True)
    valor = models.PositiveIntegerField()
    
    def __str__(self):
        return self.tipo
