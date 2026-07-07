from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User, Profile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create a profile when a new user is created.
    """
    if created:
        Profile.objects.get_or_create(
            user=instance,
            defaults={
                "display_name": instance.phone_number,
            },
        )


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Save the related profile whenever the user is saved.
    """
    try:
        instance.profile.save()
    except Profile.DoesNotExist:
        pass