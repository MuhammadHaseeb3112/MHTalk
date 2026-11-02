# Generated for chat semantics and Message model consistency.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chat", "0017_chatclear")]

    operations = [
        migrations.AlterField(
            model_name="message",
            name="client_message_id",
            field=models.CharField(blank=True, db_index=True, default="", help_text="Optional client idempotency key.", max_length=64),
        ),
        migrations.AddField(
            model_name="chatclear",
            name="hide_from_list",
            field=models.BooleanField(db_index=True, default=True, help_text="Hide the conversation from the chat list until a newer message arrives."),
        ),
    ]
