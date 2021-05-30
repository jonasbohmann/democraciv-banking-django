from django.urls import include, path
from rest_framework import routers
from rest_framework.authtoken import views as auth_views

from bank.api.v1 import views

router = routers.DefaultRouter()
router.register(r'account', views.AccountViewSet, basename='Account')
router.register(r'corporation', views.CorporationViewSet, basename='Corporation')
router.register(r'featured_corporation', views.FeaturedCorporationViewSet, basename='FeaturedCorporation')
router.register(r'transaction', views.TransactionViewSet, basename='Transaction')
router.register(r'user', views.UserViewSet)


urlpatterns = [
    path('', include(router.urls)),
    path('accounts/<int:discord_id>/', views.AccountsPerDiscordUser.as_view()),
    path('discord_user/<int:discord_id>/', views.UserAccountFromDiscordUser.as_view()),
    path('send/', views.TransactionCreate.as_view()),
    path('statistics/', views.BankStatistics.as_view()),
    path('default_account/', views.DefaultBankAccount.as_view()),
    path('ottoman/apply/', views.ApplyOttomanFormula.as_view()),
    path('ottoman/threshold/', views.OttomanThresholds.as_view()),
    path('currencies/', views.CurrenciesView.as_view()),
    path('token/', auth_views.obtain_auth_token),
    path('auth/', include('rest_framework.urls', namespace='rest_framework'))
]
