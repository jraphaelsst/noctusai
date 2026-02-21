from django.urls import include, path
from rest_framework import routers

from proprietario.viewsets import ProprietarioViewSet

router = routers.SimpleRouter()
router.register(r'', ProprietarioViewSet, basename='proprietario')


urlpatterns = [
    path('', include(router.urls))
]
