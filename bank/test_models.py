from django.test import TestCase
from djmoney.money import Money
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from . import models


class AccountTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username="test", password="test")
        self.another_user = get_user_model().objects.create(username="foo", password="bar")
        self.a_third_user = get_user_model().objects.create(
            username="lore", password="dana")
        self.corporation = models.Corporation.objects.create(
            owner=self.user, name="A", abbreviation="ABC")
        models.Employee.objects.create(
            corporation=self.corporation, person=self.a_third_user)

    def test_account_creation(self):
        pers_account = models.Account.objects.create(
            individual_holder=self.user)
        self.assertIsInstance(pers_account.holder, get_user_model())

        corp_account = models.Account.objects.create(
            corporate_holder=self.corporation)
        self.assertIsInstance(corp_account.holder, models.Corporation)

        self.assertEqual(pers_account.balance, Money(
            0, pers_account.balance_currency))

        self.assertEqual(pers_account.pretty_holder, "test")
        self.assertEqual(corp_account.pretty_holder, "A")

        self.assertEqual(pers_account.holder, self.user)
        self.assertEqual(corp_account.holder, self.corporation)

        self.assertEqual(pers_account.owner, self.user)
        self.assertEqual(corp_account.owner, self.user)

        illegal_account = models.Account.objects.create(
            individual_holder=self.user, corporate_holder=self.corporation)

        with self.assertRaises(ValidationError):
            illegal_account.clean()

    def test_account_creation_with_currency(self):
        pers_account = models.Account.objects.create(
            individual_holder=self.user, currency="CIV")
        pers_account.clean()

        self.assertNotEqual(pers_account.balance, Money(0, 'USD'))
        self.assertEqual(pers_account.balance, Money(0, 'CIV'))

    def test_account_creation_with_discord(self):
        pers_account = models.Account.objects.create(
            individual_holder=self.user)
        self.assertListEqual(pers_account.get_discord_ids(), [])

        self.user.discord_id = 1
        self.user.save()

        self.assertListEqual(pers_account.get_discord_ids(), [1])

    def test_account_permissions(self):
        pers_account = models.Account.objects.create(
            individual_holder=self.user)
        corp_account = models.Account.objects.create(
            corporate_holder=self.corporation)

        self.assertTrue(self.user.has_perm('bank.view_account', pers_account))
        self.assertTrue(self.user.has_perm(
            'bank.change_account', pers_account))
        self.assertTrue(self.user.has_perm(
            'bank.delete_account', pers_account))

        self.assertFalse(self.another_user.has_perm(
            'bank.view_account', pers_account))
        self.assertFalse(self.another_user.has_perm(
            'bank.change_account', pers_account))
        self.assertFalse(self.another_user.has_perm(
            'bank.delete_account', pers_account))

        self.assertTrue(self.user.has_perm('bank.view_account', corp_account))
        self.assertTrue(self.user.has_perm(
            'bank.change_account', corp_account))
        self.assertTrue(self.user.has_perm(
            'bank.delete_account', corp_account))

        self.assertFalse(self.another_user.has_perm(
            'bank.view_account', corp_account))
        self.assertFalse(self.another_user.has_perm(
            'bank.change_account', corp_account))
        self.assertFalse(self.another_user.has_perm(
            'bank.delete_account', corp_account))

        self.assertTrue(self.a_third_user.has_perm(
            'bank.view_account', corp_account))
        self.assertFalse(self.a_third_user.has_perm(
            'bank.change_account', corp_account))
        self.assertFalse(self.a_third_user.has_perm(
            'bank.delete_account', corp_account))


class CorporationTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username="test", password="test")
        self.corporation = models.Corporation.objects.create(
            owner=self.user, name="A", abbreviation="ABC")
        self.second_user = get_user_model().objects.create(
            username="second", password="user", discord_id=2)
        self.third_user = get_user_model().objects.create(
            username="third", password="user")
        models.Employee.objects.create(
            corporation=self.corporation, person=self.second_user)
        models.Employee.objects.create(
            corporation=self.corporation, person=self.third_user)

    def test_corporation_creation(self):
        self.assertEqual(self.corporation.owner, self.user)

        self.assertEqual(self.corporation.nation,
                         models.Corporation.Nations.JAPAN)
        self.assertEqual(self.corporation.organization_type,
                         models.Corporation.OrganizationTypes.CORPORATION)
        self.assertTrue(self.corporation.is_public_viewable)
        self.assertIsNone(self.corporation.industry)
        self.assertQuerysetEqual(self.corporation.employee_set.all().order_by('person_id'),
                                 ['<Employee: second (ABC)>', '<Employee: third (ABC)>'])

    def test_corporation_with_discord(self):
        self.assertListEqual(self.corporation.get_discord_ids(), [2])

        self.user.discord_id = 1
        self.user.save()

        self.assertListEqual(self.corporation.get_discord_ids(), [2, 1])

    def test_corporation_permissions(self):
        self.assertTrue(self.user.has_perm(
            'bank.view_corporation', self.corporation))
        self.assertTrue(self.user.has_perm(
            'bank.change_corporation', self.corporation))
        self.assertTrue(self.user.has_perm(
            'bank.delete_corporation', self.corporation))
        self.assertTrue(self.user.has_perm(
            'bank.manage_employees', self.corporation))
        self.assertTrue(self.user.has_perm(
            'bank.add_corp_account', self.corporation))

        self.assertTrue(self.second_user.has_perm(
            'bank.view_corporation', self.corporation))
        self.assertTrue(self.second_user.has_perm(
            'bank.add_corp_account', self.corporation))

        self.assertTrue(self.third_user.has_perm(
            'bank.view_corporation', self.corporation))
        self.assertTrue(self.third_user.has_perm(
            'bank.add_corp_account', self.corporation))

        self.assertFalse(self.second_user.has_perm(
            'bank.manage_employees', self.corporation))
        self.assertFalse(self.second_user.has_perm(
            'bank.delete_corporation', self.corporation))
        self.assertTrue(self.second_user.has_perm(
            'bank.change_corporation', self.corporation))

        self.assertFalse(self.third_user.has_perm(
            'bank.manage_employees', self.corporation))
        self.assertFalse(self.third_user.has_perm(
            'bank.delete_corporation', self.corporation))
        self.assertTrue(self.third_user.has_perm(
            'bank.change_corporation', self.corporation))

    def test_corporation_account_permissions(self):
        unemployed = get_user_model().objects.create(username="juju", password="44")
        c_account = models.Account.objects.create(
            corporate_holder=self.corporation)

        self.assertTrue(self.user.has_perm('bank.view_account', c_account))
        self.assertTrue(self.second_user.has_perm(
            'bank.view_account', c_account))
        self.assertTrue(self.third_user.has_perm(
            'bank.view_account', c_account))
        self.assertFalse(unemployed.has_perm('bank.view_account', c_account))

        self.assertTrue(self.user.has_perm('bank.change_account', c_account))
        self.assertTrue(self.user.has_perm('bank.delete_account', c_account))

        self.assertFalse(self.second_user.has_perm(
            'bank.change_account', c_account))
        self.assertFalse(self.second_user.has_perm(
            'bank.delete_account', c_account))
        self.assertFalse(self.third_user.has_perm(
            'bank.change_account', c_account))
        self.assertFalse(self.third_user.has_perm(
            'bank.delete_account', c_account))
        self.assertFalse(unemployed.has_perm('bank.change_account', c_account))
        self.assertFalse(unemployed.has_perm('bank.delete_account', c_account))

        self.corporation.employee_set.all().delete()

        self.assertFalse(self.second_user.has_perm(
            'bank.view_account', c_account))
        self.assertFalse(self.third_user.has_perm(
            'bank.view_account', c_account))
        self.assertTrue(self.user.has_perm('bank.view_account', c_account))


class TransactionTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username="test", password="test")
        self.second_user = get_user_model().objects.create(
            username="second", password="user", discord_id=2)
        self.third_user = get_user_model().objects.create(
            username="third", password="user")

        self.account_1 = models.Account.objects.create(
            individual_holder=self.user)
        self.account_2 = models.Account.objects.create(
            individual_holder=self.second_user)

    def test_sending_money(self):
        self.account_1.balance = Money(25, 'USD')
        self.account_1.save()

        self.account_2.balance = Money(50, 'USD')
        self.account_2.save()

        models.Transaction.objects.create(from_account=self.account_1,
                                          to_account=self.account_2,
                                          amount=Money(1, 'USD'))

        self.assertEqual(self.account_1.balance, Money(24, 'USD'))
        self.assertEqual(self.account_2.balance, Money(51, 'USD'))

        models.Transaction.objects.create(from_account=self.account_2,
                                          to_account=self.account_1,
                                          amount=Money(51, 'USD'))

        self.assertEqual(self.account_1.balance, Money(75, 'USD'))
        self.assertEqual(self.account_2.balance, Money(0, 'USD'))

    def test_from_account_frozen(self):
        self.account_1.balance = Money(25, 'USD')
        self.account_1.is_frozen = True
        self.account_1.save()

        self.account_2.balance = Money(50, 'USD')
        self.account_2.save()

        with self.assertRaises(ValidationError):
            transaction = models.Transaction.objects.create(from_account=self.account_1,
                                                            to_account=self.account_2,
                                                            amount=Money(1, 'USD'))
            transaction.clean()

    def test_to_account_frozen(self):
        self.account_1.balance = Money(25, 'USD')
        self.account_1.save()

        self.account_2.balance = Money(50, 'USD')
        self.account_2.is_frozen = True
        self.account_2.save()

        with self.assertRaises(ValidationError):
            transaction = models.Transaction.objects.create(from_account=self.account_1,
                                                            to_account=self.account_2,
                                                            amount=Money(1, 'USD'))
            transaction.clean()

    def test_not_enough_money(self):
        with self.assertRaises(ValidationError):
            transaction = models.Transaction.objects.create(from_account=self.account_1,
                                                            to_account=self.account_2,
                                                            amount=Money(1, 'USD'))
            transaction.clean()

    def test_identical_from_and_to_account(self):
        self.account_1.balance = Money(25, 'USD')
        self.account_1.save()

        with self.assertRaises(ValidationError):
            transaction = models.Transaction.objects.create(from_account=self.account_1,
                                                            to_account=self.account_1,
                                                            amount=Money(2, 'USD'))
            transaction.clean()

    def test_wrong_currency(self):
        account_3 = models.Account.objects.create(
            individual_holder=self.third_user, balance=Money(5, 'XYZ'))

        with self.assertRaises(ValidationError):
            transaction = models.Transaction(from_account=account_3,
                                             to_account=self.account_1,
                                             amount=Money(2, 'XYZ'))
            transaction.clean()
