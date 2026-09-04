from rest_framework.routers import DefaultRouter
from tipo_imovel.viewsets import TipoImovelViewSet

router = DefaultRouter()
router.register(r'', TipoImovelViewSet, basename='tipo_imovel')

urlpatterns = router.urls
