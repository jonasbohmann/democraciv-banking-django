import decimal

from django import forms
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.contrib.auth import get_user_model
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import RegexValidator, MinValueValidator

from djmoney.settings import CURRENCY_CHOICES
from guardian.shortcuts import get_objects_for_user

from . import models, util
from .tasks import discord_dm_notification


def account_exists(value):
    if not models.Account.objects.filter(pk=value).exists():
        raise forms.ValidationError("There's no bank account with that IBAN.")


def user_exists(value):
    if not get_user_model().objects.filter(username=value).exists():
        raise forms.ValidationError("There's no user with that username.")


class TransactionCreationForm(forms.ModelForm):
    from_account = forms.ModelChoiceField(queryset=None, label="From Bank Account")
    to_iban = forms.UUIDField(validators=[account_exists],
                              label="To IBAN",
                              error_messages={
                                  'invalid': "Enter a valid IBAN."},
                              help_text="Every bank account has its own International Bank Account Number (IBAN).",
                              widget=forms.TextInput(attrs={'placeholder': 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'}))
    amount = forms.DecimalField(max_digits=14, decimal_places=2, validators=[
        MinValueValidator(decimal.Decimal('0.01'))])

    class Meta:
        model = models.Transaction
        fields = ['from_account', 'to_iban', 'amount', 'purpose']

    def clean(self):
        super().clean()

        if self.errors:
            return

        self.instance.to_account = models.Account.objects.get(
            pk=self.cleaned_data.get('to_iban'))

        # useful for corporate accounts, see which employee sent it
        self.instance.authorized_by = self.request.user

    def save(self, **kwargs):
        if not self.request.user.has_perm('bank.view_account', self.instance.from_account):
            raise forms.ValidationError("You don't have access to that bank account.")

        return super().save()

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)
        self.fields['from_account'].queryset = get_objects_for_user(
            self.request.user, 'bank.view_account')


class PersonalAccountCreationForm(forms.ModelForm):
    currency = forms.ChoiceField(choices=CURRENCY_CHOICES)

    class Meta:
        model = models.Account
        fields = ['name', 'currency', 'is_default_for_currency']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)
        self.fields['name'].initial = f"{self.request.user}'s Bank Account"
        self.fields['name'].help_text = "Only you can see the name you give your bank account."


class CorporateAccountCreationForm(PersonalAccountCreationForm):
    corporation = forms.ModelChoiceField(queryset=None, label="Organization")

    class Meta:
        model = models.Account
        fields = ['name', 'currency', 'corporation', 'is_default_for_currency']

    def clean(self):
        super().clean()

        if self.errors:
            return

        self.instance.corporate_holder = self.cleaned_data.get('corporation')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        employed_corporations = get_objects_for_user(
            self.request.user, 'bank.add_corp_account')
        self.fields['corporation'].queryset = employed_corporations
        self.fields['name'].initial = f"{self.request.user}'s Bank Account"
        self.fields['name'].help_text = "Only you and your employees can see this name."


class AccountUpdateForm(forms.ModelForm):
    class Meta:
        model = models.Account
        fields = ['name', 'is_default_for_currency']


class UserRegisterForm(UserCreationForm):
    class Meta:
        model = get_user_model()
        fields = ['username', 'password1', 'password2']


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ['username', 'discord_dms_enabled']


class EmployeeInvitationForm(forms.ModelForm):
    username = forms.CharField(max_length=150, validators=[user_exists])

    class Meta:
        model = models.EmployeeInvitation
        fields = ['username']

    def __init__(self, *args, **kwargs):
        self.corporation = kwargs.pop('corporation')
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()

        if self.errors:
            return

        user = get_user_model().objects.get(username=self.cleaned_data.get('username'))

        if self.corporation.employee_set.filter(person=user).exists():
            raise forms.ValidationError(
                f"{user.username} is already an employee of yours.")

        if self.corporation.employeeinvitation_set.filter(potential_employee=user).exists():
            raise forms.ValidationError(
                f"There's still a pending invite for {user.username}.")

        if self.corporation.owner == user:
            raise forms.ValidationError(
                f"{user.username} is the owner of this organization, you can't invite them to join as an employee.")

        self.instance.potential_employee = user
        self.instance.corporation = self.corporation


class CorporationCreateForm(forms.ModelForm):
    discord_server = forms.CharField(required=False,
                                     validators=[RegexValidator(regex=r'(?:https?://)?discord(?:(?:app)?\.com/'
                                                                      r'invite|\.gg)/?[a-zA-Z0-9]+/?',
                                                                message="Enter a valid Discord invite.")],
                                     help_text="You can leave this blank.",
                                     label="Discord Server")
    is_public_viewable = forms.BooleanField(help_text="Your organization will show up on "
                                                      "the Marketplace if you publish it, and people will be able "
                                                      "to send money to your "
                                                      "organization without having to specify "
                                                      "an IBAN with the Democraciv Discord Bot.",
                                            label="Publish Organization", required=False, initial=True)

    class Meta:
        model = models.Corporation
        fields = ['name', 'abbreviation', 'description', 'discord_server',
                  'nation', 'organization_type', 'industry', 'is_public_viewable']


class CorporationUpdateForm(CorporationCreateForm):
    class Meta:
        model = models.Corporation
        fields = ['name', 'description', 'discord_server', 'nation', 'organization_type', 'industry',
                  'is_public_viewable']


class PasswordResetFormWithoutEmail(forms.Form):
    username = forms.CharField(max_length=150, validators=[user_exists])

    def save(self, *args, **kwargs):
        username = self.cleaned_data["username"]
        user = get_user_model().objects.get(username=username)

        if not user.discord_id:
            return

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        url = f"https://democracivbank.com{reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})}"

        embed = util.make_embed(title="Password Reset",
                                description=f"Someone has requested a password reset for your "
                                            f"user account. Follow [this link]({url}) if that someone "
                                            f"was you.\n\nIf you did not request this reset, you can just ignore this.",
                                url=url)

        payload = {'targets': [user.discord_id], 'message': '', 'embed': embed}
        discord_dm_notification(payload)
