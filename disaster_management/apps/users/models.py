# users/models.py
from django.contrib.gis.db import models as gis_models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from django.db import models
import random
from datetime import timedelta

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_staff', True)
        # sensible defaults
        extra_fields.setdefault('first_name', extra_fields.get('first_name', ''))
        extra_fields.setdefault('last_name', extra_fields.get('last_name', ''))
        extra_fields.setdefault('role', extra_fields.get('role', 'Admin'))
        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    class RoleChoices(models.TextChoices):
        CITIZEN = "Citizen", "Citizen"
        RESPONDER = "Responder", "Responder"
        ADMIN = "Admin", "Admin"

    first_name = models.CharField(max_length=150)
    last_name  = models.CharField(max_length=150)
    email      = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, unique=True)
    location   = gis_models.PointField(geography=True, null=True, blank=True)

    role       = models.CharField(max_length=20, choices=RoleChoices.choices, default=RoleChoices.CITIZEN)

    is_verified = models.BooleanField(default=False)
    is_active   = models.BooleanField(default=True)
    is_staff    = models.BooleanField(default=False)

    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"



class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_otps")
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    @staticmethod
    def generate_otp():
        """Generate a 6-digit numeric OTP"""
        return str(random.randint(100000, 999999))

    @classmethod
    def create_for_user(cls, user):
        """Create and return a fresh OTP (invalidate older ones)"""
        cls.objects.filter(user=user, is_used=False).update(is_used=True)
        otp = cls.objects.create(user=user, code=cls.generate_otp())
        return otp

    def is_valid(self):
        """Check if OTP is within 10 minutes and not used"""
        expiry = self.created_at + timedelta(minutes=10)
        return timezone.now() <= expiry and not self.is_used

    def mark_used(self):
        self.is_used = True
        self.save(update_fields=["is_used"])

    def __str__(self):
        return f"OTP for {self.user.email} - {self.code}"