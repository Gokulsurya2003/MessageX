from django.db import models


class ChatUser(models.Model):
    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128, default="")
    gender = models.CharField(max_length=10)
    is_matched = models.BooleanField(default=False)
    is_online = models.BooleanField(default=False)
    matched_with = models.CharField(max_length=100, null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.username


class BlockedUser(models.Model):
    blocker = models.ForeignKey(
        ChatUser,
        on_delete=models.CASCADE,
        related_name="blocked_users"
    )

    blocked = models.ForeignKey(
        ChatUser,
        on_delete=models.CASCADE,
        related_name="blocked_by_users"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["blocker", "blocked"],
                name="unique_blocked_user"
            )
        ]

    def __str__(self):
        return f"{self.blocker.username} blocked {self.blocked.username}"


class Report(models.Model):
    reporter = models.ForeignKey(
        ChatUser,
        on_delete=models.CASCADE,
        related_name="reports_made"
    )

    reported = models.ForeignKey(
        ChatUser,
        on_delete=models.CASCADE,
        related_name="reports_received"
    )

    reason = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.reporter.username} reported {self.reported.username}"


class MobileSignup(models.Model):
    username = models.CharField(max_length=100)
    email = models.EmailField()
    password = models.CharField(max_length=128)
    gender = models.CharField(max_length=10)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username