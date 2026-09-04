from django.db import models

from authsys.models import User


class Proprietario(models.Model):
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    corretor = models.ForeignKey('corretor.Corretor', on_delete=models.SET_NULL, null=True, blank=True)
    nome = models.CharField(max_length=50)
    telefone = models.CharField(max_length=50)
    email = models.EmailField(blank=True, default='')
    
    class Meta:
        verbose_name = 'Proprietário'
        verbose_name_plural = 'Proprietários'
        ordering = ['nome']
        indexes = [
            models.Index(fields=['nome']),
            models.Index(fields=['corretor']),
            models.Index(fields=['telefone']),
            models.Index(fields=['email']),
        ]
    
    def __str__(self):
        return self.nome