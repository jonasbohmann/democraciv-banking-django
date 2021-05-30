import decimal
import uuid

from django.dispatch import receiver
from django.urls import reverse
from guardian.shortcuts import assign_perm, remove_perm
from django.db.models.signals import post_save, post_delete

from . import models
from . import util
from .tasks import discord_dm_notification


@receiver(post_save, sender=models.Account)
def set_ottoman_variable(sender, instance, created, **kwargs):
    if instance.currency == "LRA" and created:
        instance.ottoman_threshold_variable = decimal.Decimal("0")
        instance.save()


@receiver(post_save, sender=models.Employee)
def set_employee_permissions(sender, instance, **kwargs):
    assign_perm('bank.view_corporation',
                user_or_group=instance.person, obj=instance.corporation)
    assign_perm('bank.add_corp_account',
                user_or_group=instance.person, obj=instance.corporation)
    assign_perm('bank.view_account', user_or_group=instance.person,
                obj=instance.corporation.account_set.all())
    assign_perm('bank.change_corporation',
                user_or_group=instance.person, obj=instance.corporation)


@receiver(post_delete, sender=models.Employee)
def remove_employee_permissions(sender, instance, **kwargs):
    remove_perm('bank.view_corporation',
                user_or_group=instance.person, obj=instance.corporation)
    remove_perm('bank.change_corporation',
                user_or_group=instance.person, obj=instance.corporation)
    remove_perm('bank.add_corp_account',
                user_or_group=instance.person, obj=instance.corporation)
    remove_perm('bank.view_account', user_or_group=instance.person,
                obj=instance.corporation.account_set.all())


@receiver(post_save, sender=models.Corporation)
def set_corporation_permissions(sender, instance, **kwargs):
    assign_perm('bank.view_corporation',
                user_or_group=instance.owner, obj=instance)
    assign_perm('bank.change_corporation',
                user_or_group=instance.owner, obj=instance)
    assign_perm('bank.delete_corporation',
                user_or_group=instance.owner, obj=instance)
    assign_perm('bank.manage_employees',
                user_or_group=instance.owner, obj=instance)
    assign_perm('bank.add_corp_account',
                user_or_group=instance.owner, obj=instance)

    # in case ownership was transferred
    assign_perm('bank.view_account',
                user_or_group=instance.owner, obj=instance.account_set.all())
    assign_perm('bank.change_account',
                user_or_group=instance.owner, obj=instance.account_set.all())
    assign_perm('bank.delete_account',
                user_or_group=instance.owner, obj=instance.account_set.all())


@receiver(post_delete, sender=models.Corporation)
def clear_corporation_permissions(sender, instance, **kwargs):
    for employee in instance.employee_set.all():
        remove_perm('bank.view_account',
                    user_or_group=employee.person, obj=instance.account_set.all())

    remove_perm('bank.view_account',
                user_or_group=instance.owner, obj=instance.account_set.all())
    remove_perm('bank.change_account',
                user_or_group=instance.owner, obj=instance.account_set.all())
    remove_perm('bank.delete_account', user_or_group=instance.owner, obj=instance.account_set.all())


@receiver(post_save, sender=models.Account)
def set_account_permissions(sender, instance, created, **kwargs):
    # catch the dummy "Deleted Bank Account" account
    if instance.pk == uuid.UUID('00000000-0000-0000-0000-000000000000') or not created:
        return

    assign_perm('bank.view_account',
                user_or_group=instance.owner, obj=instance)
    assign_perm('bank.change_account',
                user_or_group=instance.owner, obj=instance)
    assign_perm('bank.delete_account',
                user_or_group=instance.owner, obj=instance)

    if instance.corporate_holder:
        for employee in instance.corporate_holder.employee_set.all():
            assign_perm('bank.view_account',
                        user_or_group=employee.person, obj=instance)


@receiver(post_save, sender=models.Account)
def override_default_account(sender, instance, **kwargs):
    # catch the dummy "Deleted Bank Account" account
    if instance.pk == uuid.UUID('00000000-0000-0000-0000-000000000000') or not instance.is_default_for_currency:
        return

    for account in instance.holder.account_set.filter(currency=instance.currency, is_default_for_currency=True).exclude(
            pk=instance.pk):
        account.is_default_for_currency = False
        account.save()


@receiver(post_save, sender=models.Transaction)
def send_transaction_dm(sender, instance, created, **kwargs):
    if not created:
        return

    targets = instance.to_account.get_discord_ids()

    if not targets:
        return

    if instance.to_account.corporate_holder:
        description = "An organization you're part of has just received a transaction!"
        to_value = f"**{instance.to_account.corporate_holder}** - {instance.to_account.name}"
    else:
        description = "You have just received a transaction!"
        to_value = instance.to_account.name

    embed = util.make_embed(title="New Transaction",
                            description=description,
                            url=f"https://democracivbank.com{reverse('bank:account-transaction-detail', kwargs={'pk': str(instance.pk)})}")
    util.add_field(embed, name="From", value=instance.from_account.pretty_holder)
    util.add_field(embed, name="To", value=to_value)
    util.add_field(embed, name="Amount", value=instance.amount)
    util.add_field(embed, name="Purpose", value=instance.purpose, inline=False)
    payload = {'targets': list(set(targets)), 'message': '', 'embed': embed}

    discord_dm_notification(payload)


@receiver(post_save, sender=models.EmployeeInvitation)
def send_invite_sent_dm(sender, instance, created, **kwargs):
    if not created:
        return

    # person was invited

    target = instance.potential_employee

    if not target.discord_id or not target.discord_dms_enabled:
        return

    embed = util.make_embed(title="New Invite to Organization",
                            description=f"You were invited by **{instance.corporation.owner}** to join "
                                        f"**{instance.corporation}** as an employee.",
                            url=f"https://democracivbank.com{reverse('bank:user-employment')}")

    payload = {'targets': [target.discord_id],
               'message': '', 'embed': embed}

    discord_dm_notification(payload)


@receiver(post_delete, sender=models.EmployeeInvitation)
def send_invite_accept_reject_dm(sender, instance, **kwargs):
    targets = instance.corporation.get_discord_ids()

    if not targets:
        return

    person = instance.potential_employee

    if person.discord_id and person.discord_id in targets:
        targets.remove(person.discord_id)

    if instance.corporation.employee_set.filter(person=person).exists():
        embed = util.make_embed(title="New Employee",
                                description=f"**{person}** accepted your invite and just joined **{instance.corporation}** "
                                            f"as an employee.\n\nThey now have access to all of your organization's bank accounts and can send "
                                            f"money on behalf of your organization.",
                                url=f"https://democracivbank.com{reverse('bank:corporation-employees', kwargs={'pk': instance.corporation.pk})}")

    else:
        embed = util.make_embed(title="Invite Declined",
                                description=f"**{person}** declined your invite to join **{instance.corporation}** as an employee.",
                                url=f"https://democracivbank.com{reverse('bank:corporation-employees', kwargs={'pk': instance.corporation.pk})}")

    payload = {'targets': list(set(targets)), 'message': '', 'embed': embed}

    discord_dm_notification(payload)
