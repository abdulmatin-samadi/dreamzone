from django.urls import path

from .group_exams import GroupExamProgressView
from .monthly import MonthlyReportView
from .stats import StatsView
from .views import DashboardView, ExaminationStatsView, ResultsSummaryView

urlpatterns = [
    path("dashboard/", DashboardView.as_view()),
    path("results-summary/", ResultsSummaryView.as_view()),
    path("stats/", StatsView.as_view()),
    path("monthly/", MonthlyReportView.as_view()),
    path("group-exams/", GroupExamProgressView.as_view()),
    path("examinations/<int:pk>/", ExaminationStatsView.as_view()),
]
