import json
import time
import requests
import django_tables2 as tables

from django import http
from django.urls import reverse
from django.db import transaction
from django.conf import settings
from django.contrib import messages
from django.views import View, generic
from django_tables2 import LazyPaginator
from django_tables2.export import ExportMixin
from django.contrib.auth.views import PasswordResetView
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from djmoney.money import Money
from oauthlib.oauth2 import AccessDeniedError
from guardian.mixins import PermissionRequiredMixin
from requests_oauthlib import OAuth2Session
from guardian.shortcuts import get_objects_for_user, remove_perm

from . import forms, models, util
from .tasks import discord_dm_notification


def index(request):
    return render(request, "bank/bank.html", make_context())


def make_context(context=None):
    if context is None:
        context = {}

    context['bank_name'] = settings.BANK_NAME
    return context


def make_oauth_session(token=None, state=None):
    return OAuth2Session(
        client_id="741660720244195370",
        token=token,
        state=state,
        scope="identify",
        redirect_uri="https://democracivbank.com/discord/")


@csrf_exempt
def bot_twitch_callback(request):
    requests.post(settings.DEMOCRACIV_DISCORD_BOT_API_TWITCH_CALLBACK, headers=dict(request.headers), data=request.body)
    js = json.loads(request.body)

    if "challenge" in js:
        return http.HttpResponse(js["challenge"])

    return http.HttpResponse("ok")


@login_required()
def discord_callback(request):
    if request.method != "GET":
        return http.HttpResponseNotAllowed(permitted_methods="GET")

    discord = make_oauth_session(state=request.session['discord_oauth2_state'])

    try:
        token = discord.fetch_token("https://discord.com/api/oauth2/token",
                                    client_secret="6B9ROswLw4xYDsQv5T4WGHDE67WLXxUx",
                                    authorization_response=request.build_absolute_uri())
    except AccessDeniedError:
        messages.error(request, "You canceled the process.")
        return redirect("bank:user")

    discord = make_oauth_session(token=token)
    user_object = discord.get("https://discord.com/api/users/@me").json()
    user_id = int(user_object['id'])
    request.user.discord_id = user_id
    request.user.discord_username = f"{user_object['username']}#{user_object['discriminator']}"
    request.user.discord_profile_picture_url = f"https://cdn.discordapp.com/avatars/{user_id}/{user_object['avatar']}"
    request.user.save()
    messages.success(
        request, f"You are now connected with {request.user.discord_username}.")

    if request.user.discord_dms_enabled:
        test_embed = util.make_embed(title="Discord Account Connected",
                                     description=f"Your Discord account was just connected with democracivbank.com "
                                                 f"user {request.user.username}. If you received this DM, it worked!",
                                     url=f"https://democracivbank.com{reverse('bank:user')}")
        payload = {'targets': [user_id], 'message': '', 'embed': test_embed}
        discord_dm_notification(payload)

    return redirect("bank:user")


@login_required()
def discord_connect(request):
    if request.method != "GET":
        return http.HttpResponseNotAllowed(permitted_methods="GET")

    discord = make_oauth_session()
    authorization_url, state = discord.authorization_url(
        "https://discord.com/api/oauth2/authorize")
    request.session['discord_oauth2_state'] = state
    return render(request, "bank/discord_oauth.html",
                  make_context({'discord_url': authorization_url, 'title': 'Discord',
                                'description': "Connect your Discord Account to unlock real-time notifications, "
                                               "the bank commands of the Democraciv Discord Bot, "
                                               "as well as the 'I forgot my password' functionality."}))


class EmployeeInviteView(LoginRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        action = kwargs.get("action")

        invite = get_object_or_404(
            models.EmployeeInvitation, pk=kwargs.get("pk"))

        if invite.potential_employee != self.request.user:
            return http.HttpResponseForbidden()

        if action == 'accept':
            employee = models.Employee.objects.create(
                person=self.request.user, corporation=invite.corporation)
            employee.save()
            messages.success(
                request, f"Congratulations on joining {employee.corporation.name}!")

        elif action == 'reject':
            messages.success(
                request, f"The invite from {invite.corporation.name} was rejected.")

        else:
            return http.HttpResponseNotFound()

        invite.delete()
        return redirect('bank:user-employment')


class MarketplaceView(View):
    template_name = 'bank/marketplace.html'

    def get(self, request: http.HttpRequest, *args, **kwargs):
        featured = models.FeaturedCorporation.objects.all()
        corporations = models.Corporation.objects.filter(
            is_public_viewable=True)
        return render(request, self.template_name, make_context({'corporations': corporations, 'featured': featured,
                                                                 'title': 'Marketplace'}))


class UserProfileView(LoginRequiredMixin, View):
    form_class = forms.UserUpdateForm
    template_name = 'bank/user_profile.html'

    def get(self, request: http.HttpRequest, *args, **kwargs):
        form = self.form_class(instance=request.user)
        return render(request, self.template_name, make_context({'form': form, 'title': 'Me'}))

    def post(self, request: http.HttpRequest, *args, **kwargs):
        form = self.form_class(request.POST, instance=request.user)

        if form.is_valid():
            form.save()
            return redirect('bank:user')

        return render(request, self.template_name, make_context({'form': form,
                                                                 'title': 'Me'}))


class UserEmploymentOverviewView(LoginRequiredMixin, View):
    template_name = 'bank/user_employment.html'

    def get(self, request: http.HttpRequest, *args, **kwargs):
        invites = self.request.user.employeeinvitation_set.all()
        employed_corps = self.request.user.employed_at.all()
        return render(request, self.template_name,
                      make_context({'invites': invites, 'employed_corps': employed_corps,
                                    'title': 'Employment'}))


class LeaveCorporationView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        employee = get_object_or_404(
            models.Employee, pk=kwargs.get('employee', 0))

        if employee.person != self.request.user:
            return http.HttpResponseForbidden()

        employee.delete()

        if employee.corporation.owner.discord_id and employee.corporation.owner.discord_dms_enabled:
            embed = util.make_embed(title="Employee left Organization",
                                    description=f"**{employee.person.username}** just left **{employee.corporation.name}**.",
                                    url=f"https://democracivbank.com{reverse('bank:corporation-employees', kwargs={'pk': employee.corporation.pk})}")
            payload = {'targets': [employee.corporation.owner.discord_id], 'message': '', 'embed': embed}
            discord_dm_notification(payload)

        messages.success(request, f"You left {employee.corporation}.")
        return redirect('bank:user-employment')


class RegisterView(View):
    form_class = forms.UserRegisterForm
    template_name = 'register.html'

    def get(self, request: http.HttpRequest, *args, **kwargs):
        form = self.form_class()
        return render(request, self.template_name, make_context({'form': form, 'title': 'Sign Up'}))

    def post(self, request: http.HttpRequest, *args, **kwargs):
        form = self.form_class(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, f'Your registration was successful.')
            return redirect('bank:account')

        return render(request, self.template_name, make_context({'form': form, 'title': 'Sign Up'}))


class AccountListView(LoginRequiredMixin, tables.SingleTableView):
    table_class = models.AccountsTable
    template_name = "bank/account_list.html"
    context_object_name = 'accounts'
    model = models.Account

    def get_table_kwargs(self):
        return {'order_by': 'created_on'}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = make_context(context)
        context['title'] = "Bank Accounts"
        return context

    def get_queryset(self):
        return get_objects_for_user(self.request.user, 'bank.view_account')


class AccountDetailView(LoginRequiredMixin, PermissionRequiredMixin, ExportMixin, tables.SingleTableView):
    table_class = models.TransactionTable
    context_object_name = 'transactions'
    template_name = "bank/account_detail.html"
    permission_required = 'bank.view_account'
    return_404 = True
    paginator_class = LazyPaginator
    export_formats = ("csv", "json", "xlsx")

    def get_table_kwargs(self):
        return {'order_by': '-created_on'}

    def get_permission_object(self):
        self.object = get_object_or_404(models.Account, pk=self.kwargs['pk'])
        return self.object

    def get_queryset(self):
        self.transactions = models.Transaction.objects.filter(from_account__iban=self.kwargs['pk']) | \
                            models.Transaction.objects.filter(
                                to_account__iban=self.kwargs['pk'])
        return self.transactions

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = make_context(context)
        context['title'] = self.object.name
        context['transactions'] = self.transactions
        context['account'] = self.object
        context['form_allowed'] = self.request.user.has_perm(
            'bank.delete_account', obj=self.object)

        self.export_name = f"democracivbank_transactions_{self.object.iban}_{time.time()}"
        return context


class AccountUpdateView(LoginRequiredMixin, PermissionRequiredMixin, generic.UpdateView):
    permission_required = 'bank.view_account'
    return_404 = True
    model = models.Account
    form_class = forms.AccountUpdateForm

    def get_permission_object(self):
        self.object = get_object_or_404(models.Account, pk=self.kwargs['pk'])
        return self.object

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['form_title'] = f"Edit {self.object.name}"
        context['form_button'] = "Confirm"
        context['title'] = f"Edit {self.object.name}"
        return make_context(context)


class AccountDeleteView(LoginRequiredMixin, PermissionRequiredMixin, generic.DeleteView):
    permission_required = 'bank.delete_account'
    return_404 = True
    model = models.Account

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['title'] = f"Delete {self.object.name}"
        return make_context(context)

    def post(self, request, *args, **kwargs):
        account = self.get_object()

        if account.balance != Money(0, account.balance.currency):
            messages.error(
                request, "You can only delete a bank account that has no money left in it.")
            return redirect('bank:account-detail', account.pk)

        messages.success(request, f"{account.name} was deleted.")
        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        return '/account'

    def get_permission_object(self):
        self.object = get_object_or_404(models.Account, pk=self.kwargs['pk'])
        return self.object


class TransactionDetailView(LoginRequiredMixin, PermissionRequiredMixin, generic.DetailView):
    model = models.Transaction
    return_404 = True

    def check_permissions(self, request):
        transaction = self.get_object()

        if request.user.has_perm('bank.view_account', transaction.to_account) or request.user.has_perm(
                'bank.view_account', transaction.from_account):
            return None

        response = render(request, "404.html")
        response.status_code = 404
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = make_context(context)
        context['title'] = "Transaction"
        transaction = self.get_object()

        if self.request.user.has_perm('bank.view_account', transaction.to_account):
            context['to'] = True

        if self.request.user.has_perm('bank.view_account', transaction.from_account):
            context['from'] = True

        return context


class TransactionCreateView(LoginRequiredMixin, View):

    def get(self, request: http.HttpRequest, *args, **kwargs):
        form = forms.TransactionCreationForm(request=self.request)
        return render(request, 'bank/transaction_form.html', make_context({'form': form, 'title': 'Send Money'}))

    def post(self, request: http.HttpRequest, *args, **kwargs):
        form = forms.TransactionCreationForm(
            request.POST, request=self.request)

        if form.is_valid():
            request.session['form_data'] = request.POST
            return redirect('bank:account-transaction-confirm')

        return render(request, 'bank/transaction_form.html', make_context({'form': form, 'title': 'Send Money'}))


class TransactionConfirmView(LoginRequiredMixin, View):

    def get(self, request: http.HttpRequest, *args, **kwargs):
        form = forms.TransactionCreationForm(
            request.session.get('form_data'), request=self.request)

        if form.is_valid():
            from_account = form.instance.from_account.name
            to_user = form.instance.to_account.pretty_holder
            amount = form.instance.amount
            iban = form.instance.to_account.iban
            old_balance = form.instance.from_account.balance
            new_balance = form.instance.from_account.balance - form.instance.amount
            return render(request, 'bank/transaction_confirm_form.html', make_context({'form': form,
                                                                                       'iban': iban,
                                                                                       'from_account': from_account,
                                                                                       'to_user': to_user,
                                                                                       'amount': amount,
                                                                                       'old_balance': old_balance,
                                                                                       'new_balance': new_balance,
                                                                                       'title': 'Send Money'}))

        return http.HttpResponseNotFound()

    def post(self, request: http.HttpRequest, *args, **kwargs):
        form = forms.TransactionCreationForm(
            request.POST, request=self.request)

        if form.is_valid():
            del request.session['form_data']
            form.save()

            if request.user.has_perm('bank.view_account', form.instance.to_account):
                to_fmt = form.instance.to_account.name
            else:
                to_fmt = form.instance.to_account.pretty_holder

            messages.success(self.request,
                             f'You sent {form.instance.amount} to {to_fmt}.')

            return redirect('bank:account-transaction-detail', form.instance.id)


def account_creation_chooser(request):
    return render(request, "bank/account_create.html", make_context({'title': 'Open Bank Account'}))


class PersonalAccountCreateView(LoginRequiredMixin, generic.CreateView):
    model = models.Account
    form_class = forms.PersonalAccountCreationForm

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['form_title'] = "Open a new Bank Account"
        context['title'] = "Open Bank Account"
        context['form_button'] = "Confirm"
        return make_context(context)

    def form_valid(self, form):
        form.instance.individual_holder = self.request.user
        messages.success(
            self.request, f'Your new personal bank account was opened.')
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs


class CorporateAccountCreateView(LoginRequiredMixin, generic.CreateView):
    model = models.Account
    form_class = forms.CorporateAccountCreationForm

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['form_title'] = "Open a new Bank Account"
        context['title'] = "Open Bank Account"
        context['form_button'] = "Confirm"
        return make_context(context)

    def form_valid(self, form):
        messages.success(
            self.request, f'A new shared bank account for your organization was opened.')
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs


class CorporationCreateView(LoginRequiredMixin, generic.CreateView):
    model = models.Corporation
    form_class = forms.CorporationCreateForm

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['form_title'] = "Form a new Organization"
        context['title'] = "Form Organization"
        context['form_button'] = "Confirm"
        return make_context(context)

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class CorporationDeleteView(LoginRequiredMixin, PermissionRequiredMixin, generic.DeleteView):
    model = models.Corporation
    permission_required = 'bank.delete_corporation'
    return_403 = True

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['title'] = "Delete Organization"
        return make_context(context)

    def get_success_url(self):
        return '/organization'

    def get_permission_object(self):
        self.object = get_object_or_404(
            models.Corporation, pk=self.kwargs['pk'])
        return self.object


class CorporationListView(LoginRequiredMixin, tables.SingleTableView):
    model = models.Corporation
    table_class = models.CorporationTable
    context_object_name = 'corporations'

    def get_table_kwargs(self):
        return {'order_by': '-created_on'}

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['title'] = "My Organizations"
        return make_context(context)

    def get_queryset(self):
        return get_objects_for_user(user=self.request.user, perms='bank.view_corporation')


class ManageEmployeeView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'bank.view_corporation'
    return_403 = True
    template_name = 'bank/corporation_employees.html'
    form_class = forms.EmployeeInvitationForm

    def get(self, request, *args, **kwargs):
        corp = get_object_or_404(models.Corporation, pk=kwargs.get('pk'))
        form = self.form_class(corporation=corp)
        invites = corp.employeeinvitation_set.all()
        employees = corp.employee_set.all()
        can_manage = request.user.has_perm("bank.manage_employees", corp)

        return render(request, self.template_name,
                      make_context({'corporation': corp, 'employees': employees, 'form': form, 'invites': invites,
                                    'can_manage': can_manage, 'title': f"Employees of {corp.name}"}))

    def post(self, request: http.HttpRequest, *args, **kwargs):
        corp = get_object_or_404(models.Corporation, pk=kwargs.get('pk'))
        invites = corp.employeeinvitation_set.all()
        employees = corp.employee_set.all()
        form = self.form_class(request.POST, corporation=corp)
        can_manage = request.user.has_perm("bank.manage_employees", corp)

        if form.is_valid():
            form.save()
            messages.success(request, f"{form.instance.potential_employee.username} was invited.")
            return redirect('bank:corporation-employees', kwargs.get('pk'))

        return render(request, self.template_name,
                      make_context({'corporation': corp, 'employees': employees, 'form': form,
                                    'title': f"Employees of {corp.name}",
                                    'invites': invites, 'can_manage': can_manage}))

    def get_permission_object(self):
        return get_object_or_404(models.Corporation, pk=self.kwargs['pk'])


class FireEmployeeView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'bank.manage_employees'
    return_403 = True

    def get(self, request, *args, **kwargs):
        employee = get_object_or_404(
            models.Employee, pk=kwargs.get('employee', 0))
        employee.delete()

        if employee.person.discord_id and employee.person.discord_dms_enabled:
            embed = util.make_embed(title="You were Fired",
                                    description=f"**{employee.corporation.owner.username}** just fired you, "
                                                f"and you are no longer an employee of **{employee.corporation.name}**.",
                                    url=f"https://democracivbank.com{reverse('bank:user')}")
            payload = {'targets': [employee.person.discord_id], 'message': '', 'embed': embed}
            discord_dm_notification(payload)

        messages.success(request, f"{employee.person.username} was fired.")
        return redirect('bank:corporation-employees', kwargs.get('pk'))

    def get_permission_object(self):
        return get_object_or_404(models.Corporation, pk=self.kwargs.get('pk', ''))


class TransferOwnershipView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'bank.manage_employees'
    return_403 = True

    def get(self, request, *args, **kwargs):
        employee = get_object_or_404(
            models.Employee, pk=kwargs.get('employee', 0))
        return render(request, "bank/corporation_confirm_transfer_ownership.html",
                      make_context({'new_owner': employee.person.username, 'org': employee.corporation.name}))

    def post(self, request, *args, **kwargs):
        employee = get_object_or_404(models.Employee, pk=kwargs.get('employee', 0))
        new_owner = employee.person
        corp = employee.corporation
        employee.delete()

        with transaction.atomic():
            models.Employee.objects.create(corporation=corp, person=self.request.user)
            corp.owner = new_owner
            corp.save()

            remove_perm('bank.delete_corporation',
                        user_or_group=self.request.user, obj=corp)
            remove_perm('bank.manage_employees',
                        user_or_group=self.request.user, obj=corp)

            remove_perm('bank.change_account',
                        user_or_group=self.request.user, obj=corp.account_set.all())
            remove_perm('bank.delete_account',
                        user_or_group=self.request.user, obj=corp.account_set.all())

        embed = util.make_embed(title="New Owner of Organization",
                                description=f"**{new_owner.username}** was just made the new owner of "
                                            f"**{corp.name}**. The previous owner was {self.request.user.username}.",
                                url=f"https://democracivbank.com{reverse('bank:corporation-employees', kwargs={'pk': kwargs.get('pk')})}")
        payload = {'targets': corp.get_discord_ids(), 'message': '', 'embed': embed}
        discord_dm_notification(payload)

        messages.success(request, f"{employee.person.username} is the new owner.")
        return redirect('bank:corporation-employees', kwargs.get('pk'))

    def get_permission_object(self):
        return get_object_or_404(models.Corporation, pk=self.kwargs.get('pk', ''))


class CorporateUpdateView(LoginRequiredMixin, PermissionRequiredMixin, generic.UpdateView):
    permission_required = 'bank.change_corporation'
    return_403 = True
    model = models.Corporation
    template_name = "bank/corporation_form.html"
    form_class = forms.CorporationUpdateForm

    def get_permission_object(self):
        self.object = get_object_or_404(models.Corporation, pk=self.kwargs['pk'])
        return self.object

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context['form_title'] = f"Edit {self.object.name}"
        context['form_button'] = "Confirm"
        context['title'] = f"Edit {self.object.name}"
        return make_context(context)


class CorporationDetailView(UserPassesTestMixin, generic.DetailView):
    model = models.Corporation
    context_object_name = 'corporation'
    form_class = forms.CorporationUpdateForm
    table_class = models.CorporateAccountsTable

    def post(self, request, *args, **kwargs):
        obj = self.get_object()

        if not self.request.user.has_perm('bank.change_corporation', obj=obj):
            return http.HttpResponseForbidden()

        form = self.form_class(request.POST, instance=obj)

        if form.is_valid():
            form.save()
            return redirect('bank:corporation-detail', obj.pk)

        return render(request, self.template_name, make_context({'form': form, 'title': "Organization"}))

    def is_employed(self, corp):
        if self.request.user.is_anonymous:
            return False

        if corp.employee_set.filter(person=self.request.user).exists() or self.is_boss(corp):
            return True

        return False

    def is_boss(self, corp):
        return self.request.user == corp.owner

    def test_func(self):
        corp = self.get_object()

        if corp.is_public_viewable:
            return True
        else:
            return self.request.user.has_perm('bank.view_corporation', obj=corp)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context = make_context(context)
        corp = context['corporation']
        is_employed = self.is_employed(corp)
        context['is_employed'] = is_employed
        context['is_boss'] = self.is_boss(corp)
        context['title'] = corp.name

        if is_employed:
            table = self.table_class(corp.account_set.all())
            context['table'] = table

        return context


def bot_resubmit_view(request, discord_id):
    return render(request, "bank/discord_id_view.html", make_context({"discord_id": discord_id}))


class PasswordResetViewNoEmail(PasswordResetView):
    form_class = forms.PasswordResetFormWithoutEmail
    extra_context = make_context()
