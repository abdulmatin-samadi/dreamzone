from django.urls import include, path

urlpatterns = [
    path("auth/", include("apps.accounts.auth_urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.academics.urls")),
    path("", include("apps.students.urls")),
    path("", include("apps.questions.urls")),
    path("", include("apps.examinations.urls")),
    path("", include("apps.results.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("", include("apps.audit.urls")),
]
