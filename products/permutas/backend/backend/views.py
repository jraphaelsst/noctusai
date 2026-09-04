import os
from django.http import HttpResponse
from django.conf import settings


def serve_react_app(request):
    index_path = os.path.join(settings.FRONTEND_BUILD_DIR, 'index.html')
    if os.path.exists(index_path):
        with open(index_path, 'r') as f:
            return HttpResponse(f.read(), content_type='text/html')
    return HttpResponse('Frontend not built', status=404)
