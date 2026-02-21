from django.urls import include, path
from rest_framework import routers

from permuta.viewsets import PermutaImovelViewSet, PermutaAutomovelViewSet


router = routers.SimpleRouter()
router.register(r'imovel', PermutaImovelViewSet, basename='permuta')
router.register(r'automovel', PermutaAutomovelViewSet, basename='permuta')


urlpatterns = [
    path('', include(router.urls))
]
