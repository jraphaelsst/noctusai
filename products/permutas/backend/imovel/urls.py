from django.urls import include, path
from rest_framework import routers

from imovel.viewsets import ImovelViewSet, InteresseImovelViewSet, InteresseAutomovelViewSet

router = routers.SimpleRouter()
router.register(r'', ImovelViewSet, basename='imovel')

interesse_router = routers.SimpleRouter()
interesse_router.register(r'imovel', InteresseImovelViewSet, basename='interesse-imovel')
interesse_router.register(r'automovel', InteresseAutomovelViewSet, basename='interesse-automovel')


urlpatterns = [
    path('', include(router.urls)),
    path('interesse/', include(interesse_router.urls)),
]
