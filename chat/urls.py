from django.urls import path 
from . import views
urlpatterns = [path("", views.home,name="home"),
               path("logout/", views.logout_user, name="logout"),
               path("reset-all-users/", views.reset_all_users, name="reset_all_users"),
               path("chat.html", views.chat,name="chat"),
               path("login/", views.login_user, name="login"),
               path("api/login/", views.api_login, name="api_login"),
               path("find-random-chat/", views.find_random_chat, name="find_random_chat"),
               path("match-status/", views.match_status, name="match_status"),
               path("disconnect-chat/", views.disconnect_chat, name="disconnect_chat"),
               path("block-user/", views.block_user, name="block_user"),
               path("report-user/", views.report_user, name="report_user"),
               path("signup.html",views.signup, name="signup"),
               path("verify-signup/", views.verify_signup, name="verify_signup"),
               path("forgot-password.html",views.forgot_password,name="forgot_password"),
               path("verify-code.html",views.verify_code,name="verify_code"),
               path("reset-password.html",views.reset_password,name="reset_password")]
