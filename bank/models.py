import uuid
import moneyed
import django_tables2 as tables

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.db import models, transaction
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import CICharField

from djmoney.models import fields


class User(AbstractUser):
    # first_time_login = models.BooleanField(default=True)
    discord_id = models.BigIntegerField(null=True, unique=True)
    discord_profile_picture_url = models.URLField(null=True)
    discord_username = models.CharField(max_length=50, null=True)
    discord_dms_enabled = models.BooleanField(
        default=True, verbose_name="Notifications via the Democraciv Discord Bot")


class Corporation(models.Model):
    name = models.CharField(unique=True, max_length=100)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL,
                              on_delete=models.CASCADE)
    abbreviation = CICharField(primary_key=True, max_length=8,
                               help_text="You cannot change the abbreviation in the future.")
    created_on = models.DateTimeField(default=timezone.now)
    description = models.TextField(max_length=1000)
    discord_server = models.CharField(
        null=True, blank=True, max_length=50, help_text="You can leave this blank.")
    is_public_viewable = models.BooleanField(default=True)

    class Meta:
        permissions = (
            ('manage_employees', 'Invite new people and fire existing employees'),
            ('add_corp_account', 'Create corporate bank account'),
        )

    class Nations(models.TextChoices):
        JAPAN = "JP", "Japan"

    nation = models.CharField(
        max_length=2,
        choices=Nations.choices,
        default=Nations.JAPAN,
        help_text="Select the nation you operate out of. Different nations may have different laws on "
                  "things like corporate tax.")

    class OrganizationTypes(models.TextChoices):
        CORPORATION = "CORP", "Corporation"
        ORGANIZATION = "ORG", "Organization"
        GOVERNMENT = "GOV", "Government Entity"
        NON_PROFIT = "NPO", "Non-Profit"
        SPECIAL_INTEREST = "SIG", "Special Interest Group"

    organization_type = models.CharField(
        max_length=4,
        choices=OrganizationTypes.choices,
        default=OrganizationTypes.CORPORATION,
        help_text="This is purely for role-playing purposes and has no effect on anything.",
        verbose_name="Type of Organization"
    )

    class Industries(models.TextChoices):
        AD = "AD", "Advertisement & Campaign Services"
        FINANCE = "F", "Financial Services"
        PRESS = "PR", "Press"
        DEFENSE = "D", "Defense"
        OTHER = "O", "Other"

    industry = models.CharField(
        max_length=2,
        choices=Industries.choices,
        null=True,
        blank=True,
        help_text="This is purely for role-playing purposes and has no effect on anything. You can leave this blank.")

    def __str__(self):
        return self.name

    def get_discord_ids(self):
        employees = self.employee_set.all()
        ids = [employee.person.discord_id for employee in employees
               if employee.person.discord_id and employee.person.discord_dms_enabled]

        if self.owner.discord_id and self.owner.discord_dms_enabled:
            ids.append(self.owner.discord_id)

        return ids

    def get_absolute_url(self):
        return reverse('bank:corporation-detail', kwargs={'pk': self.abbreviation})


class FeaturedCorporation(models.Model):
    corporation = models.OneToOneField(Corporation, on_delete=models.CASCADE)
    featured_since = models.DateTimeField(default=timezone.now)
    ad_message = models.TextField(max_length=1000)

    def __str__(self):
        return self.corporation.name


class Employee(models.Model):
    person = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employed_at")
    corporation = models.ForeignKey(Corporation, on_delete=models.CASCADE)
    employed_since = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('person', 'corporation',)

    def __str__(self):
        return f"{self.person.username} ({self.corporation.abbreviation})"


class EmployeeInvitation(models.Model):
    potential_employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    corporation = models.ForeignKey(Corporation, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('potential_employee', 'corporation',)

    def __str__(self):
        return f"{self.potential_employee.username} ({self.corporation.abbreviation})"


class Account(models.Model):
    iban = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=100, editable=True, default='Bank Account')
    balance = fields.MoneyField(max_digits=20, decimal_places=2,
                                default_currency='USD', default=0)
    currency = fields.CurrencyField()

    is_frozen = models.BooleanField(default=False)
    is_default_for_currency = models.BooleanField(verbose_name="Default Bank Account for this Currency",
                                                  default=True,
                                                  help_text="This bank account will be used when someone tries to "
                                                            "send you money in this currency without specifying an "
                                                            "IBAN, for example with the Democraciv Discord Bot. "
                                                            "You can only have one default bank account per currency.")
    created_on = models.DateTimeField(default=timezone.now)

    individual_holder = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    corporate_holder = models.ForeignKey(
        Corporation, null=True, blank=True, on_delete=models.SET_NULL)

    ottoman_threshold_variable = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    is_reserve = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    def clean(self):
        # Don't allow both a Corporation and a User to own this Account
        if self.corporate_holder and self.individual_holder:
            raise ValidationError(
                'A bank account can have either an Individual holder or a Corporate holder, not both.')

        self.balance.currency = moneyed.Currency(code=self.currency)
        self.balance_currency = self.currency

    def get_absolute_url(self):
        return reverse('bank:account-detail', kwargs={'pk': self.pk})

    @property
    def holder(self):
        return self.individual_holder if self.individual_holder else self.corporate_holder

    @property
    def owner(self):
        if self.individual_holder:
            return self.individual_holder
        elif self.corporate_holder:
            return self.corporate_holder.owner

    @property
    def pretty_holder(self):
        return str(self.holder)

    def get_discord_ids(self):
        if self.individual_holder:
            if not self.individual_holder.discord_id or not self.individual_holder.discord_dms_enabled:
                return []

            return [self.individual_holder.discord_id]

        elif self.corporate_holder:
            return self.corporate_holder.get_discord_ids()


def get_deleted_account():
    return Account.objects.get_or_create(iban=uuid.UUID('00000000-0000-0000-0000-000000000000'),
                                         name="Deleted Bank Account",
                                         is_frozen=True)[0]


class Transaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_account = models.ForeignKey(Account, on_delete=models.SET(
        get_deleted_account), related_name='transactions_from')
    to_account = models.ForeignKey(Account, on_delete=models.SET(
        get_deleted_account), related_name='transactions_to')
    amount = fields.MoneyField(max_digits=20, decimal_places=2)
    purpose = models.TextField(max_length=500, blank=True, default="", help_text="The recipient can read this. You can "
                                                                                 "leave this blank.")
    created_on = models.DateTimeField(default=timezone.now)

    authorized_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                      on_delete=models.SET_NULL,
                                      null=True)

    class TransactionState(models.TextChoices):
        SUCCESSFUL = 'SC', 'Successful'
        REVOKED = 'RV', 'Revoked'

    state = models.CharField(
        max_length=2,
        choices=TransactionState.choices,
        default=TransactionState.SUCCESSFUL,
    )

    def __str__(self):
        return str(self.id)

    def clean(self):
        try:
            if self.from_account == self.to_account:
                raise ValidationError(
                    "You cannot send money to the same bank account you're sending from.")
        except Transaction.to_account.RelatedObjectDoesNotExist:
            return

        if self.from_account.balance.currency != self.to_account.balance.currency:
            raise ValidationError(
                "You cannot send money to a bank account that has a different currency.")

        self.amount.currency = self.from_account.balance.currency
        self.amount_currency = self.amount.currency.code

        if self.amount > self.from_account.balance:
            raise ValidationError(
                'You have insufficient funds in your bank account.')

        if self.to_account.is_frozen:
            raise ValidationError('The bank account to send money to is frozen.')

        if self.from_account.is_frozen:
            raise ValidationError('Your bank account is frozen.')

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        with transaction.atomic():
            super().save(force_insert=force_insert, force_update=force_update,
                         using=using, update_fields=update_fields)
            self.from_account.balance -= self.amount
            self.from_account.save()
            self.to_account.balance += self.amount
            self.to_account.save()

    def get_absolute_url(self):
        return reverse('bank:account-transaction-detail', kwargs={'pk': self.pk})


class AccountsTable(tables.Table):
    iban = tables.Column(verbose_name="IBAN")
    name = tables.Column(linkify=True)
    corporate_holder = tables.Column(verbose_name="Organization")
    is_default_for_currency = tables.Column(verbose_name="Default for its Currency")

    class Meta:
        model = Account
        empty_text = "You don't have any bank accounts yet."
        attrs = {"class": "table table-hover table-bordered"}
        fields = ['name', 'iban', 'balance', 'corporate_holder', 'is_default_for_currency']

    def render_is_default_for_currency(self, value):
        if value:
            return format_html('<i class="fas fa-check-circle"></i>')

        return "—"


class CorporateAccountsTable(tables.Table):
    iban = tables.Column(verbose_name="IBAN")
    name = tables.Column(linkify=True)
    is_default_for_currency = tables.Column(verbose_name="Default for its Currency")

    class Meta:
        model = Account
        empty_text = "This organization does not have any bank accounts yet."
        attrs = {"class": "table table-hover table-bordered"}
        fields = ['name', 'iban', 'balance', 'is_default_for_currency']

    def render_is_default_for_currency(self, value):
        if value:
            return format_html('<i class="fas fa-check-circle"></i>')

        return "—"


class CorporationTable(tables.Table):
    name = tables.Column(linkify=True)
    created_on = tables.Column(verbose_name="Founded (UTC)")

    class Meta:
        model = Corporation
        empty_text = "You're not part of any organization."
        attrs = {"class": "table table-hover table-bordered"}
        fields = ['name', 'abbreviation', 'nation', 'owner', 'created_on']

    def render_created_on(self, value):
        return value.strftime("%A, %d %B %Y %H:%M")


class TransactionTable(tables.Table):
    transaction_id = tables.Column(verbose_name="Transaction ID", accessor="id", visible=False)
    id = tables.Column(verbose_name="", exclude_from_export=True)
    created_on = tables.Column(verbose_name="Date (UTC)")
    from_account = tables.Column(verbose_name="From")
    from_iban = tables.Column(verbose_name="From IBAN", accessor="from_account__iban", visible=False)
    to_iban = tables.Column(verbose_name="To IBAN", accessor="to_account__iban", visible=False)
    to_account = tables.Column(verbose_name="To")
    raw_amount = tables.Column(verbose_name="Raw Amount", accessor="amount__amount", visible=False)
    currency = tables.Column(verbose_name="Currency", accessor="amount__currency", visible=False)

    class Meta:
        model = Transaction
        empty_text = "This bank account hasn't had any transaction yet."
        attrs = {"class": "table table-hover table-bordered"}
        fields = ['transaction_id', 'from_account', 'from_iban', 'to_account', 'to_iban', 'amount', 'raw_amount',
                  'currency', 'created_on', 'id']

    def value_raw_amount(self, value, record):
        context_account = Account.objects.get(pk=self.request.resolver_match.kwargs['pk'])

        if context_account == record.from_account:
            return value.copy_negate()
        else:
            return value

    def render_from_account(self, value):
        if self.request.user.has_perm('bank.view_account', value):
            return value.name
        else:
            return value.pretty_holder

    def render_to_account(self, value):
        if self.request.user.has_perm('bank.view_account', value):
            return value.name
        else:
            return value.pretty_holder

    def render_amount(self, value, record):
        account = Account.objects.get(pk=self.request.resolver_match.kwargs['pk'])

        if account.pk == record.to_account.pk:
            return format_html('<p class="text-success">+{}</p>', value)
        elif account.pk == record.from_account.pk:
            return format_html('<p class="text-danger">-{}</p>', value)

    def value_amount(self, value):
        return value

    def value_id(self, value):
        return value

    def render_id(self, value):
        return format_html(
            '<a href="{}"><button class="btn btn-primary" style="margin-bottom: 10px" >Details</button></a>',
            reverse('bank:account-transaction-detail', kwargs={'pk': str(value)}))

    def render_created_on(self, value):
        return value.strftime("%A, %d %B %Y %H:%M")

    def value_created_on(self, value):
        return value
