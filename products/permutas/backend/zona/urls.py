from django.urls import include, path
from rest_framework import routers

from zona.viewsets import ZonaViewSet

router = routers.SimpleRouter()
router.register(r'', ZonaViewSet, basename='zona')


urlpatterns = [
    path('', include(router.urls))
]
