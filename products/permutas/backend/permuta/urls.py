from django.urls import include, path
from rest_framework import routers

from permuta.viewsets import (
    PermutaImovelViewSet, PermutaAutomovelViewSet, MatchViewSet,
    InteressePermutaImovelViewSet, InteressePermutaAutomovelViewSet
)


router = routers.SimpleRouter()
router.register(r'imovel', PermutaImovelViewSet, basename='permuta-imovel')
router.register(r'automovel', PermutaAutomovelViewSet, basename='permuta-automovel')
router.register(r'match', MatchViewSet, basename='match')
router.register(r'interesse-imovel', InteressePermutaImovelViewSet, basename='interesse-permuta-imovel')
router.register(r'interesse-automovel', InteressePermutaAutomovelViewSet, basename='interesse-permuta-automovel')


urlpatterns = [
    path('', include(router.urls))
]
