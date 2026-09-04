from django.urls import include, path
from rest_framework import routers

from .viewsets import CondominioViewSet

router = routers.SimpleRouter()
router.register(r'', CondominioViewSet, basename='condominio')


urlpatterns = [
    path('', include(router.urls))
]
