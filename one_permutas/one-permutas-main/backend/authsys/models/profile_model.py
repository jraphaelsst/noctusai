from django.db import models


class Profile(models.Model):
    user = models.OneToOneField(to='authsys.User', on_delete=models.CASCADE)
    full_name = models.CharField(max_length=50, null=True, blank=True)
    image = models.ImageField(default='default.jpg', upload_to='user_images', null=True, blank=True)
    bio = models.TextField(max_length=300, null=True, blank=True)
    verified = models.BooleanField(default=False)
    
    def save(self, *args, **kwargs):
        if self.full_name == "" or self.full_name == None:
            self.full_name = self.user.username
        super(Profile, self).save(*args, **kwargs)
    
    def __str__(self):
        return self.full_name
