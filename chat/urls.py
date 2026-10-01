from django.urls import path 
from . import views
urlpatterns = [path("", views.home,name="home"),
               path("logout/", views.logout_user, name="logout"),
               path("reset-all-users/", views.reset_all_users, name="reset_all_users"),
               path("chat.html", views.chat,name="chat"),
               path("login/", views.login_user, name="login"),
               path("api/login/", views.api_login, name="api_login"),
               path(
                    "api/find-random-chat/",
                    views.api_find_random_chat,
                    name="api_find_random_chat"
                    ),
               path(
                    "api/disconnect-chat/",
                    views.api_disconnect_chat,
                    name="api_disconnect_chat"
                    ),
               path(
                    "api/logout/",
                    views.api_logout,
                    name="api_logout"
                    ),

               path(
                    "api/block-user/",
                    views.api_block_user,
                    name="api_block_user"
                    ),

               path(
                    "api/report-user/",
                    views.api_report_user,
                    name="api_report_user"
                    ),
               path(
                    "api/mobile-signup/",
                    views.api_mobile_signup,
                    name="api_mobile_signup"
                    ),

               path(
                    "api/mobile-verify-otp/",
                    views.api_mobile_verify_otp,
                    name="api_mobile_verify_otp"
                    ),
               path("find-random-chat/", views.find_random_chat, name="find_random_chat"),
               path("match-status/", views.match_status, name="match_status"),
               path("disconnect-chat/", views.disconnect_chat, name="disconnect_chat"),
               path("block-user/", views.block_user, name="block_user"),
               path("report-user/", views.report_user, name="report_user"),
               path("signup.html",views.signup, name="signup"),
               path("verify-signup/", views.verify_signup, name="verify_signup"),
               path("forgot-password.html",views.forgot_password,name="forgot_password"),
               path("api/forgot-password/", views.api_forgot_password, name="api_forgot_password"),
               path("api/verify-reset-code/", views.api_verify_reset_code, name="api_verify_reset_code"),
               path("api/reset-password/", views.api_reset_password, name="api_reset_password"),
               path("verify-code.html",views.verify_code,name="verify_code"),
               path("reset-password.html",views.reset_password,name="reset_password")]
