from django.contrib import admin
from django.urls import path, include, reverse_lazy

from bank import views as bank_views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', include('bank.urls', namespace='bank')),
    path('register/', bank_views.RegisterView.as_view(template_name='bank/register.html'), name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='bank/login.html', extra_context=bank_views.make_context()), name='login'),
    path('change-password/', auth_views.PasswordChangeView.as_view(template_name='bank/change_password.html', extra_context=bank_views.make_context(), success_url=reverse_lazy('bank:user')), name="change-password"),
    path('logout/', auth_views.LogoutView.as_view(template_name='bank/logout.html', extra_context=bank_views.make_context()), name='logout'),
    path('reset-password/', bank_views.PasswordResetViewNoEmail.as_view(template_name="bank/password_reset.html"), name="password_reset"),
    path('reset-password/sent', auth_views.PasswordResetDoneView.as_view(template_name="bank/password_reset_sent.html", extra_context=bank_views.make_context()), name="password_reset_done"),
    path('reset-password/confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name="bank/password_reset_confirm.html", extra_context=bank_views.make_context()), name="password_reset_confirm"),
    path('reset-password/done', auth_views.PasswordResetCompleteView.as_view(template_name="bank/password_reset_done.html", extra_context=bank_views.make_context()), name="password_reset_complete"),
    path('admin/', admin.site.urls),
    path('twitch/callback', bank_views.bot_twitch_callback),
    path('api/v1/', include('bank.api.v1.urls')),
]
