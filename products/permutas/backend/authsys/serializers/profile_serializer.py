from rest_framework import serializers

from authsys.models import Profile


class ProfileSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Profile
        fields = '__all__'
