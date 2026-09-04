from django.db import models

from authsys.models import User


class Imovel(models.Model):
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    corretor = models.ForeignKey('corretor.Corretor', on_delete=models.SET_NULL, null=True, blank=True)
    proprietario = models.ForeignKey('proprietario.Proprietario', on_delete=models.DO_NOTHING)
    condominio = models.ForeignKey('condominio.Condominio', on_delete=models.DO_NOTHING)
    
    tipo = models.ForeignKey('tipo_imovel.TipoImovel', on_delete=models.SET_NULL, null=True, blank=True)
    zona = models.ForeignKey('zona.Zona', on_delete=models.SET_NULL, null=True, blank=True)
    ref = models.CharField(max_length=8)
    valor_venda = models.PositiveIntegerField()
    
    class Meta:
        verbose_name = 'Imóvel'
        verbose_name_plural = 'Imóveis'
        ordering = ['-id']
        indexes = [
            models.Index(fields=['tipo', 'zona']),
            models.Index(fields=['valor_venda']),
            models.Index(fields=['criado_por']),
            models.Index(fields=['corretor']),
            models.Index(fields=['ref']),
        ]
    
    def __str__(self) -> str:
        return self.ref
