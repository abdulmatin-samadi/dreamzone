from django.contrib import admin

from .models import AnswerOption, Passage, Question

admin.site.register(Passage)
admin.site.register(AnswerOption)


class OptionInline(admin.TabularInline):
    model = AnswerOption


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    inlines = [OptionInline]
    list_display = ["text", "question_type", "section", "level"]
