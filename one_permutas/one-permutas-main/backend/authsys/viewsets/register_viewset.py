from rest_framework.permissions import AllowAny#, IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from authsys.models import User
from authsys.serializers import RegisterSerializer


class RegisterViewSet(ModelViewSet):
    permission_classes = ([AllowAny])
    
    serializer_class = RegisterSerializer
    queryset = User.objects.all()
