from datetime import timedelta

from django.utils import timezone
from django.http import JsonResponse
from django.core.mail import send_mail
from django.shortcuts import render, redirect

from .models import ChatUser, BlockedUser, Report

from django.contrib.auth.hashers import check_password, make_password
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

import random
import os
import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def login_user(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip().lower()
        password = request.POST.get("password")

        user = ChatUser.objects.filter(username=username).first()

        if user and check_password(password, user.password):
            user.is_online = True
            user.save()

            request.session["username"] = user.username
            request.session["gender"] = user.gender

            return redirect("home")

        return render(request, "chat.html", {"error": "Invalid username or password!"})

    return render(request, "chat.html")


def find_random_chat(request):
    username = request.session.get("username")
    gender = request.session.get("gender")

    if not username or not gender:
        return redirect("chat")

    opposite_gender = "female" if gender == "male" else "male"

    # Current user
    current_user = ChatUser.objects.get(username=username)

    # Already matched → don't create another match
    if current_user.is_matched and current_user.matched_with:

        matched_user = ChatUser.objects.filter(
            username=current_user.matched_with, is_online=True
        ).first()

        if matched_user:
            request.session["matched_username"] = matched_user.username
            return redirect("home")

        current_user.is_matched = False
        current_user.matched_with = None
        current_user.save()

    # --------------------------------------------------
    # Remove stale online users
    # --------------------------------------------------

    cutoff = timezone.now() - timedelta(seconds=8)

    ChatUser.objects.filter(is_online=True, last_seen__lt=cutoff).update(
        is_online=False
    )

    # --------------------------------------------------
    # Find users blocked by current user
    # --------------------------------------------------

    blocked_user_ids = BlockedUser.objects.filter(blocker=current_user).values_list(
        "blocked_id", flat=True
    )

    # --------------------------------------------------
    # Find users who blocked current user
    # --------------------------------------------------

    blocked_by_user_ids = BlockedUser.objects.filter(blocked=current_user).values_list(
        "blocker_id", flat=True
    )

    # Combine both lists
    excluded_user_ids = set(blocked_user_ids).union(set(blocked_by_user_ids))

    # --------------------------------------------------
    # Find available opposite-gender users
    # --------------------------------------------------

    users = (
        ChatUser.objects.filter(
            gender=opposite_gender,
            is_matched=False,
            is_online=True,
            last_seen__gte=cutoff,
        )
        .exclude(username=username)
        .exclude(id__in=excluded_user_ids)
    )

    # --------------------------------------------------
    # Create match
    # --------------------------------------------------

    if users.exists():

        matched_user = random.choice(list(users))

        # Current user
        current_user.is_matched = True
        current_user.matched_with = matched_user.username
        current_user.save()

        # Matched user
        matched_user.is_matched = True
        matched_user.matched_with = current_user.username
        matched_user.save()

        # Notify matched user automatically
        channel_layer = get_channel_layer()

        async_to_sync(channel_layer.group_send)(
            f"user_{matched_user.username}",
            {
                "type": "match_found",
                "matched_username": current_user.username,
            },
        )

        # Save match in current session
        request.session["matched_username"] = matched_user.username
        request.session["matched_gender"] = matched_user.gender

    return redirect("home")


def home(request):
    username = request.session.get("username")

    if not username:
        return redirect("chat")

    current_user = ChatUser.objects.filter(username=username).first()

    matched_username = None

    if current_user and current_user.is_matched and current_user.matched_with:

        matched_user = ChatUser.objects.filter(
            username=current_user.matched_with
        ).first()

        # Match is valid only when:
        # both users are online
        # both users are matched
        # both point to each other
        if (
            matched_user
            and matched_user.is_online
            and matched_user.is_matched
            and matched_user.matched_with == username
        ):
            matched_username = matched_user.username

        else:
            # Clear stale match
            current_user.is_matched = False
            current_user.matched_with = None
            current_user.save()

            if matched_user:
                matched_user.is_matched = False
                matched_user.matched_with = None
                matched_user.save()

    return render(
        request,
        "home.html",
        {"username": username, "matched_username": matched_username},
    )


def chat(request):
    return render(request, "chat.html")


def signup(request):
    if request.method == "POST":

        username = request.POST.get("username", "").strip().lower()

        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")
        gender = request.POST.get("gender")

        # Check email format
        try:
            validate_email(email)

        except ValidationError:
            return render(request, "signup.html", {"error": "Invalid email ID!"})

        # Check password match
        if password != confirm_password:
            return render(request, "signup.html", {"error": "Passwords do not match!"})

        # Check username already exists
        if ChatUser.objects.filter(username=username).exists():

            return render(request, "signup.html", {"error": "Username already exists!"})

        # Check email already exists
        if ChatUser.objects.filter(email=email).exists():

            return render(
                request, "signup.html", {"error": "Email already registered!"}
            )

        # Generate OTP
        code = str(random.randint(100000, 999999))

        # Save signup details temporarily in session
        request.session["signup_code"] = code
        request.session["signup_username"] = username
        request.session["signup_email"] = email
        request.session["signup_gender"] = gender
        request.session["signup_password"] = make_password(password)

        # Send OTP using Brevo API
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": os.getenv("BREVO_API_KEY"),
                "content-type": "application/json",
            },
            json={
                "sender": {
                    "name": "MessageX",
                    "email": "suryagokul302@gmail.com"
                },
                "to": [{"email": email}],
                "subject": "MessageX Email Verification Code",
                "textContent": f"Your verification code is: {code}",
            },
        )
        print("BREVO STATUS:", response.status_code)
        print("BREVO RESPONSE:", response.text)

        if response.status_code not in [200, 201, 202]:
            return render(
                request,
                "signup.html",
                {"error": "Unable to send verification email. Please try again."},
            )

        return redirect("verify_signup")

    return render(request, "signup.html")


def verify_signup(request):
    if request.method == "POST":

        entered_code = request.POST.get("code")
        saved_code = request.session.get("signup_code")

        if entered_code == saved_code:

            ChatUser.objects.create(
                username=request.session.get("signup_username"),
                email=request.session.get("signup_email"),
                password=request.session.get("signup_password"),
                gender=request.session.get("signup_gender"),
            )

            # Clear signup data from session
            request.session.pop("signup_code", None)
            request.session.pop("signup_username", None)
            request.session.pop("signup_email", None)
            request.session.pop("signup_password", None)
            request.session.pop("signup_gender", None)

            return redirect("chat")

        return render(
            request, "verify-signup.html", {"error": "Invalid verification code!"}
        )

    return render(request, "verify-signup.html")


def forgot_password(request):
    if request.method == "POST":

        email = request.POST.get("email")

        code = str(random.randint(100000, 999999))

        request.session["reset_code"] = code

        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": os.getenv("BREVO_API_KEY"),
                "content-type": "application/json",
            },
            json={
                "sender": {
                    "name": "MessageX",
                    "email": "suryagokul302@gmail.com"
                },
                "to": [{"email": email}],
                "subject": "MessageX Password Reset Code",
                "textContent": f"Your password reset code is: {code}",
            },
        )

        print("BREVO STATUS:", response.status_code)
        print("BREVO RESPONSE:", response.text)

        if response.status_code not in [200, 201, 202]:
            return render(
                request,
                "forgot-password.html",
                {"error": "Unable to send verification email. Please try again."},
            )

        return redirect("verify_code")

    return render(request, "forgot-password.html")

def verify_code(request):
    if request.method == "POST":

        entered_code = request.POST.get("code")
        saved_code = request.session.get("reset_code")

        if entered_code == saved_code:
            return redirect("reset_password")

        return render(
            request, "verify-code.html", {"error": "Invalid verification code!"}
        )

    return render(request, "verify-code.html")


def reset_password(request):
    if request.method == "POST":

        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        if password != confirm_password:

            return render(
                request, "reset-password.html", {"error": "Passwords do not match!"}
            )

        request.session["new_password"] = password

        return redirect("chat")

    return render(request, "reset-password.html")


def disconnect_chat(request):
    username = request.session.get("username")

    if username:

        current_user = ChatUser.objects.filter(username=username).first()

        if current_user and current_user.matched_with:

            matched_username = current_user.matched_with

            matched_user = ChatUser.objects.filter(username=matched_username).first()

            # Notify matched user
            channel_layer = get_channel_layer()

            async_to_sync(channel_layer.group_send)(
                f"user_{matched_username}", {"type": "match_ended"}
            )

            # Clear matched user
            if matched_user and matched_user.matched_with == username:

                matched_user.is_matched = False
                matched_user.matched_with = None
                matched_user.save()

            # Clear current user
            current_user.is_matched = False
            current_user.matched_with = None
            current_user.save()

        request.session.pop("matched_username", None)

        request.session.pop("matched_gender", None)

    return redirect("home")


# ==================================================
# BLOCK USER
# ==================================================


def block_user(request):

    username = request.session.get("username")

    if not username:
        return JsonResponse({"success": False, "message": "Not logged in"})

    current_user = ChatUser.objects.filter(username=username).first()

    if not current_user or not current_user.matched_with:
        return JsonResponse({"success": False, "message": "No active chat"})

    blocked_user = ChatUser.objects.filter(username=current_user.matched_with).first()

    if not blocked_user:
        return JsonResponse({"success": False, "message": "User not found"})

    # Save block in database
    BlockedUser.objects.get_or_create(blocker=current_user, blocked=blocked_user)

    # Notify blocked user
    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        f"user_{blocked_user.username}", {"type": "match_ended"}
    )

    # Clear blocked user's match
    if blocked_user.matched_with == current_user.username:

        blocked_user.is_matched = False
        blocked_user.matched_with = None
        blocked_user.save()

    # Clear current user's match
    current_user.is_matched = False
    current_user.matched_with = None
    current_user.save()

    # Clear session
    request.session.pop("matched_username", None)

    request.session.pop("matched_gender", None)

    return JsonResponse({"success": True})


def report_user(request):
    username = request.session.get("username")

    if not username:
        return JsonResponse({"success": False, "message": "Not logged in"})

    current_user = ChatUser.objects.filter(username=username).first()

    if not current_user or not current_user.matched_with:
        return JsonResponse({"success": False, "message": "No active chat"})

    reported_user = ChatUser.objects.filter(username=current_user.matched_with).first()

    if not reported_user:
        return JsonResponse({"success": False, "message": "User not found"})

    reason = request.GET.get("reason", "").strip()

    if not reason:
        return JsonResponse({"success": False, "message": "Report reason is required"})

    Report.objects.create(reporter=current_user, reported=reported_user, reason=reason)

    return JsonResponse({"success": True})


def match_status(request):

    username = request.session.get("username")

    if not username:
        return JsonResponse({"matched": False})

    current_user = ChatUser.objects.filter(username=username).first()

    if not current_user:
        return JsonResponse({"matched": False})

    if current_user.is_matched and current_user.matched_with:

        matched_user = ChatUser.objects.filter(
            username=current_user.matched_with
        ).first()

        if matched_user:

            cutoff = timezone.now() - timedelta(seconds=8)

            recent_connection = (
                matched_user.last_seen and matched_user.last_seen >= cutoff
            )

            reciprocal_match = (
                matched_user.is_matched and matched_user.matched_with == username
            )

            # Refresh case:
            # user may be temporarily offline,
            # but reconnect within 8 seconds.
            if reciprocal_match and (matched_user.is_online or recent_connection):
                return JsonResponse(
                    {"matched": True, "matched_username": matched_user.username}
                )

            # Truly stale/offline → clear match
            if not recent_connection:

                current_user.is_matched = False
                current_user.matched_with = None
                current_user.save()

                if reciprocal_match:
                    matched_user.is_matched = False
                    matched_user.matched_with = None
                    matched_user.save()

    return JsonResponse({"matched": False})
