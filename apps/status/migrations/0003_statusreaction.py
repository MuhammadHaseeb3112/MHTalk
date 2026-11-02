# Generated for status reactions mirrored into private chat messages.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("status", "0002_status_visibility_statusprivacy"),
        ("chat", "0018_chatclear_hide_from_list_and_message_client_id_default"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StatusReaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("emoji", models.CharField(max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("chat_message", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="status_reactions", to="chat.message")),
                ("reactor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="status_reactions", to=settings.AUTH_USER_MODEL)),
                ("status", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reactions", to="status.status")),
            ],
            options={"db_table": "status_reactions", "ordering": ("-updated_at",)},
        ),
        migrations.AddConstraint(
            model_name="statusreaction",
            constraint=models.UniqueConstraint(fields=("status", "reactor"), name="unique_status_reaction_per_user"),
        ),
    ]
