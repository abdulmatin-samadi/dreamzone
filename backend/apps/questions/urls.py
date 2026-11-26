from rest_framework.routers import DefaultRouter

from .views import PassageViewSet, QuestionViewSet

router = DefaultRouter()
router.register("questions", QuestionViewSet, basename="question")
router.register("passages", PassageViewSet, basename="passage")
urlpatterns = router.urls
