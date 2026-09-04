from django.db import models
from django.conf import settings


class Corretor(models.Model):
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING, related_name='corretores_criados')
    nome = models.CharField(max_length=100)
    telefone = models.CharField(max_length=20, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    creci = models.CharField(max_length=20, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Corretor'
        verbose_name_plural = 'Corretores'

    def __str__(self):
        return self.nome
