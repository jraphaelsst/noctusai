from django.urls import include, path
from rest_framework import routers

from imovel.viewsets import ImovelViewSet

router = routers.SimpleRouter()
router.register(r'', ImovelViewSet, basename='imovel')


urlpatterns = [
    path('', include(router.urls))
]
