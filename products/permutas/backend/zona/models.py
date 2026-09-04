from django.db import models
from authsys.models import User


class Zona(models.Model):
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    nome = models.CharField(max_length=50, unique=True)
    descricao = models.TextField(blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Zona'
        verbose_name_plural = 'Zonas'
        ordering = ['nome']
    
    def __str__(self):
        return self.nome
