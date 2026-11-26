from django.contrib import admin

from .models import ExamAssignment, ExamAttempt, Examination, ExaminationVariant, StudentAnswer, VariantQuestion

for m in (Examination, ExaminationVariant, VariantQuestion, ExamAssignment, ExamAttempt, StudentAnswer):
    admin.site.register(m)
