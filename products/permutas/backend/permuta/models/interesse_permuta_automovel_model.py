from django.db import models
from django.core.exceptions import ValidationError

from authsys.models import User


class InteressePermutaAutomovel(models.Model):
    """
    Represents what the owner of a vehicle-in-exchange (PermutaAutomovel) accepts in return.
    
    Since vehicles are typically exchanged for properties (not other vehicles),
    this model defines property criteria that the vehicle owner would accept.
    
    For bilateral matching to work, BOTH sides need interests:
    - Imovel A has InteresseAutomovel (what A wants - a vehicle)
    - PermutaAutomovel B has InteressePermutaAutomovel (what property B's owner wants in return)
    """
    
    permuta_automovel = models.ForeignKey(
        'permuta.PermutaAutomovel',
        on_delete=models.CASCADE,
        related_name='interesses_permuta'
    )
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    
    tipo_imovel = models.ForeignKey(
        'tipo_imovel.TipoImovel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Tipo de Imóvel Desejado'
    )
    zona = models.ForeignKey(
        'zona.Zona',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Zona Desejada'
    )
    
    cep = models.CharField(max_length=20, blank=True, default='')
    estado = models.CharField(max_length=50, blank=True, default='')
    cidade = models.CharField(max_length=50, blank=True, default='')
    bairro = models.CharField(max_length=50, blank=True, default='')
    endereco = models.CharField(max_length=100, blank=True, default='')
    
    valor_minimo = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Valor mínimo aceito (null = sem mínimo)'
    )
    valor_maximo = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Valor máximo aceito (null = sem máximo)'
    )
    
    observacoes = models.TextField(blank=True, default='')
    
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Interesse de Permuta - Automóvel'
        verbose_name_plural = 'Interesses de Permuta - Automóveis'
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['permuta_automovel']),
            models.Index(fields=['tipo_imovel', 'zona']),
            models.Index(fields=['valor_minimo', 'valor_maximo']),
        ]
    
    def __str__(self):
        tipo_nome = self.tipo_imovel.nome if self.tipo_imovel else 'Qualquer tipo'
        return f"Interesse Permuta {self.permuta_automovel.codigo} - {tipo_nome}"
    
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
