from django.urls import include, path
from rest_framework import routers
from rest_framework_simplejwt.views import TokenRefreshView

from authsys.views import ObtainTokenPairView
from authsys.viewsets import RegisterViewSet

router = routers.SimpleRouter()
router.register(r'register', RegisterViewSet, basename='register')


urlpatterns = [
    path('token/', ObtainTokenPairView.as_view(), name='obtain_token'),
    path('token/refresh/', TokenRefreshView.as_view(), name='refresh_token'),
    path('', include(router.urls))
]
