from django.db import models
from django.core.mail import send_mail
from django.contrib.auth.models import PermissionsMixin, UserManager
from django.contrib.auth.base_user import AbstractBaseUser
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserModelManager(UserManager):
    """
    Case insensitive email search.
    User creation with no username.
    """

    def filter(self, **kwargs):
        if "email" in kwargs:
            kwargs["email__iexact"] = kwargs["email"]
            del kwargs["email"]
        return super(UserModelManager, self).filter(**kwargs)

    def get(self, **kwargs):
        if "email" in kwargs:
            kwargs["email__iexact"] = kwargs["email"]
            del kwargs["email"]
        return super(UserModelManager, self).get(**kwargs)

    def _create_user(self, email, password, **extra_fields):
        """
        Create and save a user with the given username, email, and password.
        """
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, username="", email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(_("email address"), unique=True)
    full_name = models.CharField(_("full name"), max_length=30, blank=True)
    # title = models.CharField(_("full name"), max_length=30, blank=True)

    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)

    position = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    photo = models.ImageField(upload_to="avatars/", null=True, blank=True)
    company = models.ForeignKey("Company", null=True, on_delete=models.PROTECT)

    objects = UserModelManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def get_full_name(self):
        """
        Returns the first_name plus the last_name, with a space in between.
        """
        return self.full_name

    def get_short_name(self):
        """
        Returns the short name for the user.
        """
        return self.full_name

    def email_user(self, subject, message, from_email=None, **kwargs):
        """
        Sends an email to this User.
        """
        send_mail(subject, message, from_email, [self.email], **kwargs)
