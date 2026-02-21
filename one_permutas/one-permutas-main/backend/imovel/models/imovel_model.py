from django.db import models

from authsys.models import User

import json


class Imovel(models.Model):
    choices_tipo = (
        ('a', 'Apartamento'),
        ('c', 'Casa'),
        ('t', 'Terreno')
    )
    
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    corretor = models.CharField(max_length=50)
    proprietario = models.ForeignKey('proprietario.Proprietario', on_delete=models.DO_NOTHING)
    condominio = models.ForeignKey('condominio.Condominio', on_delete=models.DO_NOTHING)
    
    tipo = models.CharField(max_length=1, choices=choices_tipo)
    ref = models.CharField(max_length=7)
    valor_venda = models.PositiveIntegerField()
    
    interesses_imoveis = models.CharField(max_length=1000)
    interesses_automoveis = models.CharField(max_length=1000)
    
    def __self__(self) -> str:
        return self.ref
