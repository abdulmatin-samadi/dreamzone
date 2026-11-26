from django.contrib import admin

from .models import LevelChangeHistory, StudentGroup, StudentProfile

admin.site.register(StudentProfile)
admin.site.register(StudentGroup)
admin.site.register(LevelChangeHistory)
