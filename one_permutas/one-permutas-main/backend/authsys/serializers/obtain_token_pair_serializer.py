from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class ObtainTokenPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        
        token['username'] = user.username
        token['email'] = user.email
        
        token['full_name'] = user.profile.full_name
        token['image'] = str(user.profile.image)
        token['bio'] = user.profile.bio
        token['verified'] = user.profile.verified
        
        return token
