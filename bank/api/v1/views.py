import decimal
import math

from moneyed.localization import _FORMATTER
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.urls import reverse
from djmoney.money import Money
from djmoney.settings import CURRENCY_CHOICES
from guardian.shortcuts import get_objects_for_user
from rest_framework import viewsets, status
from rest_framework import views
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework import permissions
from django.utils import timezone
from datetime import timedelta

from . import serializers
from bank import models, util
from django.conf import settings
from django.db import transaction
from ...tasks import discord_dm_notification


def calculate_ottoman_tax(account_balance: Decimal, equilibrium_balance: Decimal) -> Decimal:
    # Thanks Tiberius for providing this

    tax = (account_balance - equilibrium_balance) / 2

    pre_round_balance = account_balance - tax

    if pre_round_balance > equilibrium_balance:
        final_balance = 10 * math.floor(pre_round_balance / 10)
    else:
        final_balance = 10 * math.ceil(pre_round_balance / 10)

    final_tax = account_balance - final_balance
    return final_tax


def get_ottoman_government_account(admin_account):
    # Assume request.user is admin account
    # If not, that's not good

    bank_robot_account = models.Corporation.objects.get_or_create(name=f"Automated Payments - Bank of Arabia",
                                                                  abbreviation="AUTOBANK",
                                                                  owner=admin_account,
                                                                  is_public_viewable=False)[0]

    account = models.Account.objects.get_or_create(name="Ottoman - Automated Payments",
                                                   corporate_holder=bank_robot_account)[0]

    account.balance = Money(Decimal("1000000"), currency="LRA")
    account.currency = "LRA"
    account.save()
    return account


class AccountsPerDiscordUser(views.APIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = serializers.AccountSerializer

    def get(self, request, discord_id):
        user = get_object_or_404(get_user_model(), discord_id=discord_id)
        accounts = get_objects_for_user(user, 'bank.view_account')
        serializer = self.serializer_class(accounts, many=True)
        return Response(serializer.data)


class UserAccountFromDiscordUser(views.APIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = serializers.UserSerializer

    def get(self, request, discord_id):
        user = get_object_or_404(get_user_model(), discord_id=discord_id)
        serializer = self.serializer_class(user)
        return Response(serializer.data)


class ApplyOttomanFormula(views.APIView):
    permission_classes = [permissions.IsAdminUser]

    def apply_ottoman_formula(self, dry_run=True):
        ottoman_accounts = models.Account.objects.filter(currency="LRA").exclude(
            corporate_holder__abbreviation="AUTOBANK")
        result = {'dry_run': dry_run, 'results': []}

        with transaction.atomic():
            for account in ottoman_accounts:
                old_balance = account.balance.amount
                tax = calculate_ottoman_tax(old_balance, account.ottoman_threshold_variable)
                tax_as_money = Money(abs(tax), currency="LRA")

                if not dry_run and tax != 0:
                    if tax < 0:
                        models.Transaction.objects.create(
                            from_account=get_ottoman_government_account(self.request.user),
                            to_account=account,
                            purpose=f"Automated Tax by the Ottoman Government.\n"
                                    f"Your personal equilibrium balance is: "
                                    f"{account.ottoman_threshold_variable}",
                            amount=tax_as_money,
                            authorized_by=self.request.user)
                    else:
                        models.Transaction.objects.create(
                            from_account=account,
                            to_account=get_ottoman_government_account(
                                self.request.user),
                            purpose=f"Automated Tax by the Ottoman Government.\n"
                                    f"Your personal equilibrium balance is: "
                                    f"{account.ottoman_threshold_variable}",
                            amount=tax_as_money,
                            authorized_by=self.request.user)

                        embed = util.make_embed(title="Tax by the Ottoman Government Applied",
                                                description=f"As your bank account's balance exceeded your personal equilibrium balance ({account.ottoman_threshold_variable}), the amount of Lira specified below was automatically deducted from your bank account and sent back to the Ottoman Government as a tax.",
                                                url=f"https://democracivbank.com{reverse('bank:account-detail', kwargs={'pk': str(account.pk)})}")
                        if account.corporate_holder:
                            bank_account_value = f"**{account.pretty_holder}** - {account.name}"
                        else:
                            bank_account_value = account.name

                        util.add_field(embed, name="Bank Account", value=bank_account_value)
                        util.add_field(embed, name="Amount", value=tax_as_money)
                        payload = {'targets': account.get_discord_ids(), 'message': '', 'embed': embed}
                        discord_dm_notification(payload)

                result['results'].append({str(account.iban): {'old': old_balance, 'new': old_balance - tax,
                                                              'ibal': account.ottoman_threshold_variable}})
        return result

    def get(self, request):
        result = self.apply_ottoman_formula(dry_run=True)
        return Response(result)

    def post(self, request):
        result = self.apply_ottoman_formula(dry_run=False)
        return Response(result)


class DefaultBankAccount(views.APIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = serializers.AccountSerializer

    def get(self, request):
        discord_id = int(request.query_params.get('discord_id', 0))
        corp_id = request.query_params.get('corporation', "")

        if discord_id:
            user = get_object_or_404(get_user_model(), discord_id=discord_id)

            try:
                default_account = models.Account.objects.get(individual_holder=user, is_default_for_currency=True,
                                                             currency=request.query_params.get('currency'))
            except models.Account.DoesNotExist:
                return Response({'error': 'No default account for currency'}, status=status.HTTP_400_BAD_REQUEST)

        elif corp_id:
            corp = get_object_or_404(models.Corporation, pk=corp_id, is_public_viewable=True)

            try:
                default_account = models.Account.objects.get(corporate_holder=corp, is_default_for_currency=True,
                                                             currency=request.query_params.get('currency'))
            except models.Account.DoesNotExist:
                return Response({'error': 'No default account for currency'}, status=status.HTTP_400_BAD_REQUEST)

        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        serializer = self.serializer_class(default_account)
        return Response(serializer.data)


class CurrenciesView(views.APIView):

    def get(self, request):
        result = []

        for code, name in CURRENCY_CHOICES:
            accounts = models.Account.objects.filter(currency=code, is_reserve=False).exclude(
                corporate_holder__abbreviation="BANK")
            total_money = accounts.aggregate(Sum('balance'))['balance__sum']

            prefix, suffix = _FORMATTER.get_sign_definition(currency_code=code, locale="")

            result.append({'code': code,
                           'name': name,
                           'sign': {"prefix": prefix, "suffix": suffix},
                           'circulation': total_money})

        return Response({"result": result})


class TransactionCreate(views.APIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = serializers.WriteTransactionSerializer

    def post(self, request):
        discord_id = request.data.get('discord_id')
        user = get_object_or_404(get_user_model(), discord_id=discord_id)

        serializer = self.serializer_class(data=request.data)

        if serializer.is_valid():
            serializer.save(authorized_by=user)
            complete_transaction = serializers.ReadTransactionSerializer(serializer.instance)
            return Response(complete_transaction.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def calculate_velocity_of_money(currency_code: str) -> float:
    accounts = models.Account.objects.filter(currency=currency_code, is_reserve=False).exclude(
        corporate_holder__abbreviation="BANK")

    total_money = accounts.aggregate(Sum('balance'))['balance__sum']

    if not total_money:
        return 0.0

    transactions_in_last_seven_days = models.Transaction.objects.filter(from_account__currency=currency_code,
                                                                        created_on__gte=timezone.now() - timedelta(
                                                                            days=7))

    transaction_amounts = transactions_in_last_seven_days.aggregate(Sum('amount'))
    sent_money = transaction_amounts['amount__sum'] or decimal.Decimal("0")

    velocity = sent_money / total_money
    return velocity


class BankStatistics(views.APIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = serializers.SmallAccountSerializer

    def get(self, request):
        payload = {"total_bank_accounts": models.Account.objects.exclude(currency="XYZ").count(),
                   "total_transactions": models.Transaction.objects.all().count(),
                   'currencies': {'amount': len(settings.CURRENCIES), 'detail': {}},
                   'organizations': {}}

        for code in settings.CURRENCIES:
            payload['currencies']['detail'][code] = {
                'transactions': models.Transaction.objects.filter(from_account__currency=code).count(),
                'bank_accounts': models.Account.objects.filter(currency=code).count(),
                'velocity': calculate_velocity_of_money(code)
            }

        for nation in models.Corporation.Nations:
            payload['organizations'][nation.label] = models.Corporation.objects.filter(nation=nation).count()

        return Response(payload)


class OttomanThresholds(views.APIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = serializers.SmallAccountSerializer

    def get(self, request):
        ottoman_accounts = models.Account.objects.filter(currency="LRA").exclude(
            corporate_holder__abbreviation="AUTOBANK")
        serializer = self.serializer_class(ottoman_accounts, many=True)
        return Response(serializer.data)

    def post(self, request):
        account = get_object_or_404(models.Account, pk=request.data['iban'])
        account.ottoman_threshold_variable = request.data['new']
        account.save()
        serializer = self.serializer_class(account)
        return Response(serializer.data)


class AccountResultsSetPagination(PageNumberPagination):
    page_size = 4
    page_size_query_param = 'page_size'
    max_page_size = 1000


class AccountViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    serializer_class = serializers.AccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = AccountResultsSetPagination

    def get_queryset(self):
        return get_objects_for_user(self.request.user, 'bank.view_account').order_by('-created_on')


class CorporationViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    serializer_class = serializers.CorporationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return get_objects_for_user(self.request.user, 'bank.view_corporation').order_by('-created_on')


class FeaturedCorporationViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    queryset = models.FeaturedCorporation.objects.all().order_by('-featured_since')
    serializer_class = serializers.FeaturedCorporationSerializer
    permission_classes = [permissions.IsAdminUser]


class TransactionViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    queryset = models.Transaction.objects.all().order_by('-created_on')
    serializer_class = serializers.ReadTransactionSerializer
    permission_classes = [permissions.IsAdminUser]


class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    queryset = get_user_model().objects.all().order_by('id')
    serializer_class = serializers.UserSerializer
    permission_classes = [permissions.IsAdminUser]
