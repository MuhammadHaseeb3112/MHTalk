from __future__ import annotations
from django.contrib.auth.base_user import BaseUserManager

class UserManager(BaseUserManager):
    """
    Custom manager for the User model.
    """

    def create_user( self,  phone_number: str,  password: str | None = None,  **extra_fields,) -> User:
        """    Create and return a regular user.  """

        if not phone_number:
            raise ValueError("Phone number is required.")

        # Normalize phone number
        phone_number = (
            phone_number.strip()
            .replace(" ", "")
            .replace("-", "")
            .replace("(", "")
            .replace(")", "")
        )
        # Normalize email (optional)
        email = extra_fields.get("email")
        if email:
            extra_fields["email"] = self.normalize_email(email)

        user = self.model(  phone_number=phone_number,  **extra_fields,  )

        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(  self,  phone_number,  password=None,  **extra_fields, ):
        """   Create and return a superuser.   """

        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        if extra_fields.get("is_active") is not True:
            raise ValueError("Superuser must have is_active=True.")

        return self.create_user(  phone_number=phone_number,  password=password,  **extra_fields, )