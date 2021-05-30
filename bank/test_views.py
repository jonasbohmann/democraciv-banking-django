from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.conf import settings

from . import models


class IndexTestCase(TestCase):
    def test_index(self):
        response = self.client.get(reverse('bank:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, settings.BANK_NAME)
        self.assertContains(response, "Login")
        self.assertContains(response, "Register")


class MarketplaceTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username="Loredana", password="lorelorelore")

    def test_empty_marketplace(self):
        response = self.client.get(reverse('bank:marketplace'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerysetEqual(response.context['featured'], [])
        self.assertQuerysetEqual(response.context['corporations'], [])

    def test_marketplace_with_private_corps(self):
        models.Corporation.objects.create(name="Keine Rosen", abbreviation="LORE", owner=self.user,
                                          is_public_viewable=False)
        models.Corporation.objects.create(name="Du bist Mein", abbreviation="DANA", owner=self.user,
                                          is_public_viewable=False)

        response = self.client.get(reverse('bank:marketplace'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerysetEqual(response.context['featured'], [])
        self.assertQuerysetEqual(response.context['corporations'], [])

    def test_marketplace_with_corps(self):
        models.Corporation.objects.create(name="Keine Rosen", abbreviation="LORE", owner=self.user,
                                          is_public_viewable=True)
        models.Corporation.objects.create(name="Du bist Mein", abbreviation="DANA", owner=self.user,
                                          is_public_viewable=True)

        response = self.client.get(reverse('bank:marketplace'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerysetEqual(response.context['featured'], [])
        self.assertQuerysetEqual(response.context['corporations'],
                                 ['<Corporation: Keine Rosen>', '<Corporation: Du bist Mein>'],
                                 ordered=False)

    def test_marketplace_with_featured_corp(self):
        models.Corporation.objects.create(name="Keine Rosen", abbreviation="LORE", owner=self.user,
                                          is_public_viewable=True)
        featured = models.Corporation.objects.create(name="Du bist Mein", abbreviation="DANA", owner=self.user,
                                                     is_public_viewable=True)
        models.FeaturedCorporation.objects.create(corporation=featured, ad_message="Mein Pradaanzug schneeweiß")

        response = self.client.get(reverse('bank:marketplace'))
        self.assertEqual(response.status_code, 200)
        self.assertQuerysetEqual(response.context['featured'], ['<FeaturedCorporation: Du bist Mein>'])
        self.assertQuerysetEqual(response.context['corporations'],
                                 ['<Corporation: Keine Rosen>', '<Corporation: Du bist Mein>'],
                                 ordered=False)
