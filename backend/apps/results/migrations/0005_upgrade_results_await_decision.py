from django.db import migrations


def await_decision(apps, schema_editor):
    """Upgrade results from before "the teacher / admin decides" were failed automatically (NOT_REQUIRED).
    Under the new rule every upgrade result waits for a decision, so they get the buttons too."""
    ExamResult = apps.get_model("results", "ExamResult")
    ExamResult.objects.filter(examination__kind="UPGRADE", approval_status="NOT_REQUIRED", writing_pending=False).update(
        approval_status="PENDING")


class Migration(migrations.Migration):
    dependencies = [("results", "0004_speaking")]
    operations = [migrations.RunPython(await_decision, migrations.RunPython.noop)]
