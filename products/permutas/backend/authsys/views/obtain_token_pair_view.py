from rest_framework_simplejwt.views import TokenObtainPairView

from authsys.serializers import ObtainTokenPairSerializer

class ObtainTokenPairView(TokenObtainPairView):
    serializer_class = ObtainTokenPairSerializer
