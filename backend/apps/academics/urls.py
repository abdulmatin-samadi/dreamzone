from rest_framework.routers import DefaultRouter

from .views import GroupViewSet, LevelViewSet

router = DefaultRouter()
router.register("levels", LevelViewSet, basename="level")
router.register("groups", GroupViewSet, basename="group")
urlpatterns = router.urls
