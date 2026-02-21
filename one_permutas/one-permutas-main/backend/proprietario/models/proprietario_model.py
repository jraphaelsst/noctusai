from django.db import models

from authsys.models import User


class Proprietario(models.Model):
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    corretor = models.CharField(max_length=20)
    nome = models.CharField(max_length=50)
    telefone = models.CharField(max_length=50)
    email = models.EmailField()
    
    def __str__(self):
        return self.nome