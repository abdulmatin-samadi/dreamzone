from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path, re_path
from django.views.static import serve

def root(request):
    return HttpResponse("<h3>Dreamzone API ishlayapti.</h3>")


urlpatterns = [
    path("", root),
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.core.api_urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA:
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]
