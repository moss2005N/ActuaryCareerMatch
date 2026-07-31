from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Application user model, defined early to support future extension."""

    pass

