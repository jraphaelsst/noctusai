from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path('', include('authsys.urls')),
    path('condominio/', include('condominio.urls')),
    path('imovel/', include('imovel.urls')),
    path('proprietario/', include('proprietario.urls')),
    path('permuta/', include('permuta.urls'))
]
