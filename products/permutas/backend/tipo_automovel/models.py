from django.db import models
from authsys.models import User


class TipoAutomovel(models.Model):
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    nome = models.CharField(max_length=50, unique=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Tipo de Automóvel'
        verbose_name_plural = 'Tipos de Automóveis'
        ordering = ['nome']
    
    def __str__(self):
        return self.nome
