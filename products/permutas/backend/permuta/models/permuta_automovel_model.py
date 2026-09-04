from django.db import models

from authsys.models import User


class PermutaAutomovel(models.Model):
    choices_motor = (
        ('g', 'Gasolina'),
        ('a', 'Álcool'),
        ('f', 'Flex'),
        ('e', 'Elétrico'),
        ('h', 'Híbrido')
    )
    
    codigo = models.CharField(max_length=7, unique=True, blank=True, null=True)
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    proprietario = models.ForeignKey('proprietario.Proprietario', on_delete=models.DO_NOTHING)
    corretor = models.ForeignKey('corretor.Corretor', on_delete=models.SET_NULL, null=True, blank=True)
    tipo = models.ForeignKey('tipo_automovel.TipoAutomovel', on_delete=models.SET_NULL, null=True, blank=True)
    marca = models.CharField(max_length=20, blank=True, default='')
    modelo = models.CharField(max_length=20, blank=True, default='')
    motor = models.CharField(max_length=10, blank=True, default='')
    valor = models.PositiveIntegerField()
    
    class Meta:
        verbose_name = 'Permuta de Automóvel'
        verbose_name_plural = 'Permutas de Automóveis'
        ordering = ['-id']
        indexes = [
            models.Index(fields=['tipo']),
            models.Index(fields=['valor']),
            models.Index(fields=['corretor']),
            models.Index(fields=['marca', 'modelo']),
            models.Index(fields=['codigo']),
            models.Index(fields=['proprietario']),
        ]
    
    def __str__(self):
        return self.codigo or f'PA#{self.id}'
