# Generated manually for per-user chat clearing semantics.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0016_messagereceipt_message_client_message_id_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatClear",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cleared_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="clear_markers", to="chat.chatroom")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cleared_chats", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "chat_clears"},
        ),
        migrations.AddConstraint(
            model_name="chatclear",
            constraint=models.UniqueConstraint(fields=("room", "user"), name="unique_chat_clear_per_user"),
        ),
        migrations.AddIndex(
            model_name="chatclear",
            index=models.Index(fields=["user", "cleared_at"], name="chat_clears_user_cleared_idx"),
        ),
    ]
