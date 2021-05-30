import decimal

from django.contrib.auth import get_user_model
from djmoney.money import Money
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from bank import models


class UserSerializer(serializers.HyperlinkedModelSerializer):
    personal_accounts = serializers.PrimaryKeyRelatedField(many=True, read_only=True, source="account_set")
    employed_at = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    owns_organizations = serializers.PrimaryKeyRelatedField(many=True, read_only=True, source="corporation_set")

    class Meta:
        model = get_user_model()
        fields = ['id', 'username', 'personal_accounts', 'employed_at', 'owns_organizations', 'discord_dms_enabled']


class CorporationSerializer(serializers.HyperlinkedModelSerializer):
    owner = UserSerializer(read_only=True)
    corporate_accounts = serializers.PrimaryKeyRelatedField(many=True, read_only=True, source="account_set")
    employees = serializers.PrimaryKeyRelatedField(many=True, read_only=True, source="employee_set")
    nation = serializers.CharField(source="get_nation_display")
    organization_type = serializers.CharField(source="get_organization_type_display")
    industry = serializers.CharField(source="get_industry_display")

    class Meta:
        model = models.Corporation
        fields = ['name', 'abbreviation', 'description', 'owner', 'discord_server',
                  'is_public_viewable', 'created_on', 'nation', 'organization_type',
                  'industry', 'employees', 'corporate_accounts']
        depth = 1


class FeaturedCorporationSerializer(serializers.HyperlinkedModelSerializer):
    corporation = CorporationSerializer(read_only=True)

    class Meta:
        model = models.FeaturedCorporation
        fields = ['corporation', 'ad_message', 'featured_since']
        depth = 1


class IncompleteTransactionSerializer(serializers.HyperlinkedModelSerializer):
    from_account = serializers.PrimaryKeyRelatedField(read_only=True)
    to_account = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = models.Transaction
        fields = ['id', 'from_account', 'to_account', 'amount', 'amount_currency', 'created_on']
        depth = 1


class AccountSerializer(serializers.HyperlinkedModelSerializer):
    individual_holder = UserSerializer(read_only=True)
    corporate_holder = CorporationSerializer(read_only=True)
    transactions_to = IncompleteTransactionSerializer(many=True, read_only=True)
    transactions_from = IncompleteTransactionSerializer(many=True, read_only=True)
    pretty_balance_currency = serializers.CharField(source="get_balance_currency_display")

    class Meta:
        model = models.Account
        fields = ['iban', 'name', 'balance', 'balance_currency', 'pretty_balance_currency', 'individual_holder',
                  'corporate_holder',
                  'is_default_for_currency', 'created_on',
                  'is_frozen', 'created_on', 'ottoman_threshold_variable',
                  'transactions_to', 'transactions_from']
        depth = 1


class SmallAccountSerializer(serializers.HyperlinkedModelSerializer):
    individual_holder = serializers.PrimaryKeyRelatedField(read_only=True)
    corporate_holder = serializers.PrimaryKeyRelatedField(read_only=True)
    pretty_balance_currency = serializers.CharField(source="get_balance_currency_display")
    pretty_holder = serializers.CharField()

    class Meta:
        model = models.Account
        fields = ['iban', 'name', 'balance', 'balance_currency', 'pretty_balance_currency', 'individual_holder',
                  'corporate_holder', 'pretty_holder',
                  'is_default_for_currency', 'created_on',
                  'is_frozen', 'created_on', 'ottoman_threshold_variable']


class WriteTransactionSerializer(serializers.HyperlinkedModelSerializer):
    from_account = serializers.PrimaryKeyRelatedField(queryset=models.Account.objects.all())
    to_account = serializers.PrimaryKeyRelatedField(queryset=models.Account.objects.all())

    class Meta:
        model = models.Transaction
        fields = ['id', 'from_account', 'to_account', 'amount', 'amount_currency', 'purpose']

    def create(self, validated_data):
        obj = models.Transaction(**validated_data)
        obj.clean()
        obj.save()
        return obj

    def validate(self, data):
        to_acc = data['to_account']
        from_acc = data['from_account']
        amount = data['amount']

        if amount < decimal.Decimal('0.01'):
            raise ValidationError("You cannot send less money than 0.01")

        try:
            if from_acc == to_acc:
                raise ValidationError(
                    "You cannot send money to the same bank account you're sending from.")
        except (models.Transaction.to_account.RelatedObjectDoesNotExist,
                models.Transaction.from_account.RelatedObjectDoesNotExist):
            raise ValidationError("Not sure what happened")

        if from_acc.balance.currency != to_acc.balance.currency:
            raise ValidationError(
                "You cannot send money to a bank account that has a different currency.")

        money = Money(amount, currency=to_acc.balance.currency)

        if money > from_acc.balance:
            raise ValidationError(
                'You have insufficient funds in your bank account.')

        if to_acc.is_frozen:
            raise ValidationError('The bank account to send money to is frozen.')

        if from_acc.is_frozen:
            raise ValidationError('Your bank account is frozen.')

        return data


class ReadTransactionSerializer(serializers.HyperlinkedModelSerializer):
    authorized_by = UserSerializer(read_only=True)
    from_account = AccountSerializer(read_only=True)
    to_account = AccountSerializer(read_only=True)
    pretty_amount_currency = serializers.CharField(source="get_amount_currency_display")
    safe_to_account = serializers.CharField(source="to_account.pretty_holder")

    class Meta:
        model = models.Transaction
        fields = ['id', 'from_account', 'to_account', 'amount', 'amount_currency', 'pretty_amount_currency', 'purpose',
                  'created_on',
                  'authorized_by', 'safe_to_account']
        depth = 2
