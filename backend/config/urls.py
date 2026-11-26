from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

def root(request):
    return HttpResponse(
        '<h3>Dreamzone API ishlayapti.</h3><p>Sayt: <a href="http://localhost:5173">http://localhost:5173</a></p>'
    )


urlpatterns = [
    path("", root),
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.core.api_urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
