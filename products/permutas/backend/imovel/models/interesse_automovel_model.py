from django.db import models
from django.core.exceptions import ValidationError
from authsys.models import User


class InteresseAutomovel(models.Model):
    imovel = models.ForeignKey(
        'imovel.Imovel',
        on_delete=models.CASCADE,
        related_name='interesses_automoveis_rel'
    )
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    
    tipo_automovel = models.ForeignKey('tipo_automovel.TipoAutomovel', on_delete=models.SET_NULL, null=True, blank=True)
    valor_minimo = models.PositiveIntegerField(null=True, blank=True)
    valor_maximo = models.PositiveIntegerField(null=True, blank=True)
    
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
        verbose_name = 'Interesse de Automóvel'
        verbose_name_plural = 'Interesses de Automóveis'
        indexes = [
            models.Index(fields=['imovel']),
            models.Index(fields=['tipo_automovel']),
            models.Index(fields=['valor_minimo', 'valor_maximo']),
        ]
    
    def __str__(self):
        return f'Interesse Automóvel #{self.id} - Imóvel {self.imovel.ref}'
