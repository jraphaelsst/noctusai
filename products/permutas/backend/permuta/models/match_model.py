from django.db import models
from django.db.models import CheckConstraint, Q
from django.core.exceptions import ValidationError

from authsys.models import User


class Match(models.Model):
    ETAPA_CHOICES = (
        ('novo', 'Novo Match'),
        ('avaliacao', 'Avaliação'),
        ('negociacao', 'Negociação'),
        ('fechado', 'Fechado'),
        ('rejeitado', 'Rejeitado'),
    )
    
    codigo = models.CharField(max_length=7, unique=True, blank=True, null=True)
    permuta_imovel = models.ForeignKey(
        'permuta.PermutaImovel',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='matches'
    )
    permuta_automovel = models.ForeignKey(
        'permuta.PermutaAutomovel',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='matches'
    )
    imovel = models.ForeignKey(
        'imovel.Imovel',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='matches'
    )
    imovel_match = models.ForeignKey(
        'imovel.Imovel',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='matches_como_match'
    )
    interesse_imovel = models.ForeignKey(
        'imovel.InteresseImovel',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='matches'
    )
    interesse_automovel = models.ForeignKey(
        'imovel.InteresseAutomovel',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='matches'
    )
    etapa_do_funil = models.CharField(
        max_length=20,
        choices=ETAPA_CHOICES,
        default='novo'
    )
    ordem = models.IntegerField(default=0)
    is_bilateral = models.BooleanField(
        default=False,
        help_text='True if match was created by bilateral matching system'
    )
    observacoes = models.TextField(blank=True, default='')
    criado_por = models.ForeignKey(User, on_delete=models.DO_NOTHING, related_name='matches_criados')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    
    def clean(self):
        """Ensure exactly ONE match source is set."""
        super().clean()
        
        sources = [
            bool(self.permuta_imovel_id or self.permuta_imovel),
            bool(self.permuta_automovel_id or self.permuta_automovel),
            bool(self.imovel_match_id or self.imovel_match)
        ]
        
        if sum(sources) != 1:
            raise ValidationError(
                "O Match deve ter exatamente UMA fonte: permuta_imovel, "
                "permuta_automovel, ou imovel_match."
            )
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Match'
        verbose_name_plural = 'Matches'
        ordering = ['ordem', '-criado_em']
        constraints = [
            models.UniqueConstraint(
                fields=['imovel', 'permuta_imovel'],
                name='unique_imovel_permuta_imovel',
                condition=models.Q(permuta_imovel__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['imovel', 'permuta_automovel'],
                name='unique_imovel_permuta_automovel',
                condition=models.Q(permuta_automovel__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['imovel', 'imovel_match'],
                name='unique_imovel_imovel_match',
                condition=models.Q(imovel_match__isnull=False)
            ),
            CheckConstraint(
                check=(
                    Q(permuta_imovel__isnull=False, permuta_automovel__isnull=True, imovel_match__isnull=True) |
                    Q(permuta_imovel__isnull=True, permuta_automovel__isnull=False, imovel_match__isnull=True) |
                    Q(permuta_imovel__isnull=True, permuta_automovel__isnull=True, imovel_match__isnull=False)
                ),
                name='match_exactly_one_source'
            ),
        ]
        indexes = [
            models.Index(fields=['imovel']),
            models.Index(fields=['etapa_do_funil']),
            models.Index(fields=['etapa_do_funil', 'ordem']),
            models.Index(fields=['-criado_em']),
            models.Index(fields=['codigo']),
            models.Index(fields=['permuta_imovel']),
            models.Index(fields=['permuta_automovel']),
            models.Index(fields=['is_bilateral']),
        ]
    
    def __str__(self):
        return self.codigo or f'Match #{self.id}'
