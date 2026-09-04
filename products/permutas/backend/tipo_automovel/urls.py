from rest_framework.routers import DefaultRouter
from tipo_automovel.viewsets import TipoAutomovelViewSet

router = DefaultRouter()
router.register(r'', TipoAutomovelViewSet, basename='tipo_automovel')

urlpatterns = router.urls
