from django.db import models

from authsys.models import User


class PermutaImovel(models.Model):
    codigo = models.CharField(max_length=7, unique=True, blank=True, null=True)
    ref = models.CharField(max_length=50, blank=True, null=True)
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    proprietario = models.ForeignKey('proprietario.Proprietario', on_delete=models.DO_NOTHING)
    corretor = models.ForeignKey('corretor.Corretor', on_delete=models.SET_NULL, null=True, blank=True)
    tipo = models.ForeignKey('tipo_imovel.TipoImovel', on_delete=models.SET_NULL, null=True, blank=True)
    condominio = models.CharField(max_length=50, blank=True, default='', null=True)
    zona = models.ForeignKey('zona.Zona', on_delete=models.SET_NULL, null=True, blank=True)
    cep = models.CharField(max_length=20, blank=True, default='')
    estado = models.CharField(max_length=50, blank=True, default='')
    cidade = models.CharField(max_length=50, blank=True, default='')
    bairro = models.CharField(max_length=50, blank=True, default='')
    endereco = models.CharField(max_length=100, blank=True, default='')
    numero = models.PositiveIntegerField(blank=True, null=True)
    valor = models.PositiveIntegerField()
    
    class Meta:
        verbose_name = 'Permuta de Imóvel'
        verbose_name_plural = 'Permutas de Imóveis'
        ordering = ['-id']
        indexes = [
            models.Index(fields=['tipo', 'zona']),
            models.Index(fields=['valor']),
            models.Index(fields=['corretor']),
            models.Index(fields=['estado', 'cidade']),
            models.Index(fields=['codigo']),
            models.Index(fields=['bairro']),
            models.Index(fields=['cidade']),
            models.Index(fields=['proprietario']),
        ]
    
    def __str__(self):
        return self.codigo or f'PI#{self.id}'
