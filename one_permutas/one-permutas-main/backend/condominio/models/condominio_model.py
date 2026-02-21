from django.db import models

from authsys.models import User


class Condominio(models.Model):
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    nome = models.CharField(max_length=50)
    cep = models.CharField(max_length=20)
    estado = models.CharField(max_length=50)
    cidade = models.CharField(max_length=50)
    bairro = models.CharField(max_length=50)
    endereco = models.CharField(max_length=100)
    numero = models.PositiveIntegerField()
    km = models.PositiveIntegerField()
    valor_condominio = models.PositiveIntegerField()
    
    def __str__(self):
        return self.nome
