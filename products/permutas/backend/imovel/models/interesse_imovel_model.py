from django.db import models
from django.core.exceptions import ValidationError
from authsys.models import User


class InteresseImovel(models.Model):
    imovel = models.ForeignKey(
        'imovel.Imovel',
        on_delete=models.CASCADE,
        related_name='interesses_imoveis_rel'
    )
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    
    tipo_imovel = models.ForeignKey('tipo_imovel.TipoImovel', on_delete=models.SET_NULL, null=True, blank=True)
    zona = models.ForeignKey('zona.Zona', on_delete=models.SET_NULL, null=True, blank=True)
    cep = models.CharField(max_length=20, blank=True, default='')
    estado = models.CharField(max_length=50, blank=True, default='')
    cidade = models.CharField(max_length=50, blank=True, default='')
    bairro = models.CharField(max_length=50, blank=True, default='')
    endereco = models.CharField(max_length=100, blank=True, default='')
    valor_minimo = models.PositiveIntegerField(null=True, blank=True)
    valor_maximo = models.PositiveIntegerField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    
    def clean(self):
        """Validate that valor_minimo <= valor_maximo."""
        super().clean()
        
        if self.valor_minimo is not None and self.valor_maximo is not None:
            if self.valor_minimo > self.valor_maximo:
                raise ValidationError({
                    'valor_minimo': 'O valor mínimo não pode ser maior que o valor máximo.',
                    'valor_maximo': 'O valor máximo não pode ser menor que o valor mínimo.'
                })
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Interesse Imobiliário'
        verbose_name_plural = 'Interesses Imobiliários'
        indexes = [
            models.Index(fields=['imovel']),
            models.Index(fields=['tipo_imovel', 'zona']),
            models.Index(fields=['valor_minimo', 'valor_maximo']),
        ]
    
    def __str__(self):
        return f'Interesse Imobiliário #{self.id} - Imóvel {self.imovel.ref}'
