from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("examinations", views.ExaminationViewSet, basename="examination")
router.register("variants", views.VariantViewSet, basename="variant")
router.register("assignments", views.AssignmentViewSet, basename="assignment")
router.register("placements", views.PlacementViewSet, basename="placement")
router.register("stopped-attempts", views.StoppedAttemptViewSet, basename="stopped-attempt")
router.register("live-attempts", views.LiveAttemptViewSet, basename="live-attempt")
router.register("my/assignments", views.MyAssignmentsView, basename="my-assignment")

urlpatterns = [
    path("assignments/<int:pk>/start/", views.StartAssignmentView.as_view()),
    path("attempts/<int:pk>/", views.AttemptView.as_view()),
    path("attempts/<int:pk>/answers/", views.AttemptAnswersView.as_view()),
    path("attempts/<int:pk>/fullscreen/", views.AttemptFullscreenView.as_view()),
    path("attempts/<int:pk>/submit/", views.AttemptSubmitView.as_view()),
] + router.urls
