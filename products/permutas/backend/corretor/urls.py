from rest_framework.routers import DefaultRouter
from corretor.viewsets import CorretorViewSet

router = DefaultRouter()
router.register(r'', CorretorViewSet, basename='corretor')

urlpatterns = router.urls
