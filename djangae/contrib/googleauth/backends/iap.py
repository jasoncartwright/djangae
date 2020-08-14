import logging
import random
import string

from django.contrib.auth import get_user_model
from django.db import (
    connections,
    router,
)

from djangae.contrib.googleauth.models import UserManager

from .base import BaseBackend

User = get_user_model()


def _generate_unused_username(ideal):
    """
        Check the database for a user with the specified username
        and return either that ideal username, or an unused generated
        one using the ideal username as a base
    """

    if not User.objects.filter(username_lower=ideal.lower()).exists():
        return ideal

    exists = True

    # We use random digits rather than anything sequential to avoid any kind of
    # attack vector to get this loop stuck
    while exists:
        random_digits = "".join([random.choice(string.digits) for x in range(5)])
        username = "%s-%s" % (ideal, random_digits)
        exists = User.objects.filter(username_lower=username.lower).exists()

    return username


class IAPBackend(BaseBackend):

    @classmethod
    def can_authenticate(cls, request):
        return "HTTP_X_GOOG_AUTHENTICATED_USER_ID" in request.META and \
            "HTTP_X_GOOG_AUTHENTICATED_USER_EMAIL" in request.META

    def authenticate(self, request, **kwargs):
        connection = connections[router.db_for_read(User)]

        # FIXME: When Django GCloud Connectors gets rid of its own atomic decorator
        # the Django atomic() decorator can be used regardless
        if connection.settings_dict['ENGINE'] == 'gcloudc.db.backends.datastore':
            from gcloudc.db.transaction import atomic
        else:
            from django.db.transaction import atomic

        user_id = request.META.get("HTTP_X_GOOG_AUTHENTICATED_USER_ID")
        email = request.META.get("HTTP_X_GOOG_AUTHENTICATED_USER_EMAIL")

        # User not logged in to IAP
        if not user_id or not email:
            return

        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            logging.warning("Invalid IAP user id: %s", user_id)
            return

        email = UserManager.normalize_email(email)
        assert email

        username = email.split("@", 1)[0]

        with atomic():
            # Look for a user, either by ID, or email
            user = User.objects.filter(google_iap_id=user_id).first()
            if not user:
                # We explicitly don't do an OR query here, because we only want
                # to search by email if the user doesn't exist by ID. ID takes
                # precendence.
                user = User.objects.filter(email_lower=email.lower()).first()

                if user and user.google_iap_id:
                    logging.warning(
                        "Found an existing user by email (%s) who had a different "
                        "IAP user ID (%s != %s). This seems like a bug.",
                        email, user.google_iap_id, user_id
                    )

                    # We don't use this to avoid accidentally "stealing" another
                    # user
                    user = None

            if user:
                # So we previously had a user sign in by email, but not
                # via IAP, so we should set that ID
                if not user.google_iap_id:
                    user.google_iap_id = user_id
                else:
                    # Should be caught above if this isn't the case
                    assert(user.google_iap_id == user_id)

                # Update the email as it might have changed or perhaps
                # this user was added through some other means and the
                # sensitivity of the email differs etc.
                user.email = email

                # Note we don't update the username, as that may have
                # been overridden by something post-creation
                user.save()
            else:
                with atomic():
                    # First time we've seen this user
                    user = User.objects.create(
                        google_iap_id=user_id,
                        email=email,
                        username=_generate_unused_username(username)
                    )

        return user
