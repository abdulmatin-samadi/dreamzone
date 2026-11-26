from rest_framework.routers import DefaultRouter

from .views import TeacherViewSet, UserViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("teachers", TeacherViewSet, basename="teacher")
urlpatterns = router.urls
