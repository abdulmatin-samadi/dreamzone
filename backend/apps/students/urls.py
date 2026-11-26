from rest_framework.routers import DefaultRouter

from .views import LevelHistoryViewSet, StudentViewSet

router = DefaultRouter()
router.register("students", StudentViewSet, basename="student")
router.register("level-history", LevelHistoryViewSet, basename="level-history")
urlpatterns = router.urls
