from django.contrib import admin
from .models import (
    PermutaImovel, PermutaAutomovel, Match,
    InteressePermutaImovel, InteressePermutaAutomovel
)


@admin.register(PermutaImovel)
class PermutaImovelAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'proprietario', 'tipo', 'zona', 'valor']
    list_filter = ['tipo', 'zona']
    search_fields = ['codigo', 'proprietario__nome']


@admin.register(PermutaAutomovel)
class PermutaAutomovelAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'proprietario', 'tipo', 'marca', 'modelo', 'valor']
    list_filter = ['tipo', 'marca']
    search_fields = ['codigo', 'proprietario__nome', 'modelo']


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'etapa_do_funil', 'criado_em']
    list_filter = ['etapa_do_funil', 'criado_em']
    search_fields = ['codigo']


@admin.register(InteressePermutaImovel)
class InteressePermutaImovelAdmin(admin.ModelAdmin):
    list_display = ['permuta_imovel', 'tipo_imovel', 'zona', 'valor_minimo', 'valor_maximo', 'criado_em']
    list_filter = ['tipo_imovel', 'zona', 'criado_em']
    search_fields = ['permuta_imovel__codigo', 'observacoes']
    raw_id_fields = ['permuta_imovel', 'criado_por']


@admin.register(InteressePermutaAutomovel)
class InteressePermutaAutomovelAdmin(admin.ModelAdmin):
    list_display = ['permuta_automovel', 'tipo_imovel', 'zona', 'valor_minimo', 'valor_maximo', 'criado_em']
    list_filter = ['tipo_imovel', 'zona', 'criado_em']
    search_fields = ['permuta_automovel__codigo', 'observacoes']
    raw_id_fields = ['permuta_automovel', 'criado_por']
