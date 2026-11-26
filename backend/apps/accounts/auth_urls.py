from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .authentication import SessionTokenRefreshSerializer

from .views import (
    CaptchaView, ChangePasswordView, ChangeUsernameView, LoginView, LogoutView, MeView, PublicLevelsView, RegisterView,
    SessionRevokeOthersView, SessionRevokeView, SessionsView,
)

urlpatterns = [
    path("login/", LoginView.as_view()),
    path("refresh/", TokenRefreshView.as_view(serializer_class=SessionTokenRefreshSerializer)),
    path("levels/", PublicLevelsView.as_view()),
    path("captcha/", CaptchaView.as_view()),
    path("register/", RegisterView.as_view()),
    path("logout/", LogoutView.as_view()),
    path("me/", MeView.as_view()),
    path("change-password/", ChangePasswordView.as_view()),
    path("change-username/", ChangeUsernameView.as_view()),
    path("sessions/", SessionsView.as_view()),
    path("sessions/revoke-others/", SessionRevokeOthersView.as_view()),
    path("sessions/<uuid:sid>/revoke/", SessionRevokeView.as_view()),
]
