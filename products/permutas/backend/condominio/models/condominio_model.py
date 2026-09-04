from django.db import models

from authsys.models import User


class Condominio(models.Model):
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    nome = models.CharField(max_length=100, blank=True, null=True)
    cep = models.CharField(max_length=50, blank=True, null=True)
    estado = models.CharField(max_length=100, blank=True, null=True)
    cidade = models.CharField(max_length=100, blank=True, null=True)
    bairro = models.CharField(max_length=100, blank=True, null=True)
    endereco = models.CharField(max_length=200, blank=True, null=True)
    numero = models.IntegerField(blank=True, null=True)
    km = models.IntegerField(blank=True, null=True)
    valor_condominio = models.IntegerField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'Condomínio'
        verbose_name_plural = 'Condomínios'
        ordering = ['nome']
        indexes = [
            models.Index(fields=['nome']),
            models.Index(fields=['estado', 'cidade']),
            models.Index(fields=['bairro']),
            models.Index(fields=['cidade']),
        ]
    
    def __str__(self) -> str:
        return self.nome
