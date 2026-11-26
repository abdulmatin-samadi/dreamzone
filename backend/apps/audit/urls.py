from rest_framework.routers import DefaultRouter

from .views import AuditActionsView, AuditLogViewSet

router = DefaultRouter()
router.register("audit-log", AuditLogViewSet, basename="audit-log")
router.register("audit-actions", AuditActionsView, basename="audit-actions")
urlpatterns = router.urls
