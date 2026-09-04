from django.contrib import admin
from django.urls import include, path, re_path
from django.conf import settings
from django.conf.urls.static import static
from .views import serve_react_app

urlpatterns = [
    path("admin/", admin.site.urls),
    path('api/', include('authsys.urls')),
    path('api/condominio/', include('condominio.urls')),
    path('api/corretor/', include('corretor.urls')),
    path('api/imovel/', include('imovel.urls')),
    path('api/proprietario/', include('proprietario.urls')),
    path('api/permuta/', include('permuta.urls')),
    path('api/zona/', include('zona.urls')),
    path('api/tipo-imovel/', include('tipo_imovel.urls')),
    path('api/tipo-automovel/', include('tipo_automovel.urls')),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += [
    re_path(r'^(?!api/).*$', serve_react_app, name='react_app'),
]
