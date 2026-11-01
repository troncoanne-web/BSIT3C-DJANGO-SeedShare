from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import SeedEntry, SeedImage, SeedOrder, SeedRating, SeedTradeRequest


def make_seed_image(name, color):
    buffer = BytesIO()
    Image.new('RGB', (4, 4), color=color).save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


class SeedListTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='seed-user',
            password='test-password-123',
        )
        self.url = reverse('seeds:list')

    def test_guest_can_browse_seed_list(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Community seeds')
        self.assertContains(response, 'Create account')

    def test_guest_can_browse_from_site_homepage(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Community seeds')
        self.assertContains(response, 'Sign in')

    def test_seed_search_matches_name_case_insensitively(self):
        matching_entry = SeedEntry.objects.create(
            user=self.user,
            name='Roma Tomato',
            kind=SeedEntry.Kind.HAVE,
            offer_type=SeedEntry.OfferType.FREE,
        )
        SeedEntry.objects.create(
            user=self.user,
            name='Sunflower',
            kind=SeedEntry.Kind.WANT,
        )

        response = self.client.get(self.url, {'q': 'rOmA'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, matching_entry.name)
        self.assertNotContains(response, 'Sunflower')
        self.assertEqual(response.context['search_query'], 'rOmA')

    def test_seed_search_matches_details_and_preserves_kind_filter(self):
        matching_entry = SeedEntry.objects.create(
            user=self.user,
            name='Roma',
            kind=SeedEntry.Kind.HAVE,
            offer_type=SeedEntry.OfferType.TRADE,
            trade_for='Purple pepper seeds',
        )
        SeedEntry.objects.create(
            user=self.user,
            name='Pepper',
            kind=SeedEntry.Kind.WANT,
        )

        response = self.client.get(self.url, {'kind': 'have', 'q': 'purple'})

        self.assertContains(response, matching_entry.name)
        self.assertNotContains(response, 'Pepper</h3>')
        self.assertContains(response, 'name="kind" value="have"')
        self.assertContains(response, '?kind=have&amp;q=purple')

    def test_search_form_is_available_on_seed_board(self):
        response = self.client.get(self.url)

        self.assertContains(response, 'role="search"')
        self.assertContains(response, 'placeholder="Search by seed name, variety, or details"')

    def test_seed_board_displays_rating_summary_with_star_icon(self):
        entry = SeedEntry.objects.create(
            user=self.user,
            name='Rated tomato seeds',
            kind=SeedEntry.Kind.HAVE,
            offer_type=SeedEntry.OfferType.FREE,
        )
        SeedRating.objects.create(entry=entry, user=self.user, score=4)

        response = self.client.get(self.url)

        self.assertContains(response, 'class="seed-rating-summary mt-2"')
        self.assertContains(response, 'fas fa-star')
        self.assertContains(response, '4.0')
        self.assertContains(response, '(1 rating)')

    def test_guest_can_open_seed_post_detail_from_board(self):
        entry = SeedEntry.objects.create(
            user=self.user,
            name='Roma Tomato',
            kind=SeedEntry.Kind.HAVE,
            offer_type=SeedEntry.OfferType.TRADE,
            trade_for='Pepper seeds',
            description='Open-pollinated seeds',
            quantity=20,
            unit='packets',
            location='Cauayan',
        )

        board_response = self.client.get(self.url)
        detail_url = reverse('seeds:detail', args=[entry.pk])

        self.assertContains(board_response, detail_url)
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Roma Tomato')
        self.assertContains(response, 'Pepper seeds')
        self.assertContains(response, 'Open-pollinated seeds')
        self.assertContains(response, 'Cauayan')
        self.assertContains(response, 'Posted by seed-user')

    def test_seed_detail_is_not_found_for_missing_post(self):
        response = self.client.get(reverse('seeds:detail', args=[99999]))

        self.assertEqual(response.status_code, 404)

    def test_user_can_upload_three_seed_images_and_guests_can_view_them(self):
        self.client.force_login(self.user)
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(reverse('seeds:create'), {
                'name': 'Tomato',
                'kind': SeedEntry.Kind.HAVE,
                'offer_type': SeedEntry.OfferType.FREE,
                'quantity': 20,
                'unit': 'seeds',
                'upload_images': [
                    make_seed_image('tomato-one.png', 'red'),
                    make_seed_image('tomato-two.png', 'green'),
                    make_seed_image('tomato-three.png', 'blue'),
                ],
            })

            self.assertRedirects(response, self.url)
            entry = SeedEntry.objects.get()
            images = list(entry.images.all())
            self.assertEqual(len(images), 3)
            for image in images:
                self.assertTrue(image.image.storage.exists(image.image.name))

            board_response = self.client.get(self.url)
            self.assertContains(board_response, images[0].image.url)
            self.client.logout()
            detail_response = self.client.get(reverse('seeds:detail', args=[entry.pk]))
            self.assertEqual(detail_response.status_code, 200)
            for image in images:
                self.assertContains(detail_response, image.image.url)
            self.assertContains(detail_response, 'data-gallery-previous')
            self.assertContains(detail_response, 'data-gallery-next')
            self.assertContains(detail_response, 'data-gallery-thumbnail="2"')

    def test_seed_post_rejects_more_than_three_images(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('seeds:create'), {
            'name': 'Tomato',
            'kind': SeedEntry.Kind.HAVE,
            'offer_type': SeedEntry.OfferType.FREE,
            'quantity': 20,
            'unit': 'seeds',
            'upload_images': [
                make_seed_image(f'tomato-{index}.png', 'red')
                for index in range(4)
            ],
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A post can have up to 3 photos.')
        self.assertFalse(SeedEntry.objects.exists())

    def test_owner_can_remove_an_existing_seed_image(self):
        self.client.force_login(self.user)
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            entry = SeedEntry.objects.create(
                user=self.user,
                name='Tomato',
                kind=SeedEntry.Kind.HAVE,
                offer_type=SeedEntry.OfferType.FREE,
            )
            seed_image = SeedImage.objects.create(
                entry=entry,
                image=make_seed_image('tomato.png', 'red'),
            )
            image_name = seed_image.image.name

            response = self.client.post(reverse('seeds:edit', args=[entry.pk]), {
                'name': entry.name,
                'kind': entry.kind,
                'offer_type': entry.offer_type,
                'quantity': entry.quantity,
                'unit': entry.unit,
                'remove_images': [str(seed_image.pk)],
            })

            self.assertRedirects(response, reverse('seeds:my_posts'))
            self.assertFalse(SeedImage.objects.filter(pk=seed_image.pk).exists())
            self.assertFalse(seed_image.image.storage.exists(image_name))

    def test_guest_posting_redirects_to_login(self):
        response = self.client.post(reverse('seeds:create'), {
            'name': 'Tomato',
            'kind': SeedEntry.Kind.WANT,
            'quantity': 1,
            'unit': 'seeds',
        })

        create_url = reverse('seeds:create')
        self.assertRedirects(response, f'{reverse("login")}?next={create_url}')
        self.assertFalse(SeedEntry.objects.exists())

    def test_authenticated_user_can_open_seed_form_from_board(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertContains(response, reverse('seeds:create'))
        self.assertNotContains(response, '<form method="post">', html=False)

    def test_seed_form_allows_multiple_photo_selection_with_three_photo_limit(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('seeds:create'))

        self.assertContains(response, 'type="file"')
        self.assertContains(response, 'multiple')
        self.assertContains(response, 'Upload up to 3 JPG, PNG, or WebP images')
        self.assertContains(response, 'id="seed-upload-preview"')

    def test_authenticated_user_can_add_seed_from_create_page(self):
        self.client.force_login(self.user)
        create_url = reverse('seeds:create')
        response = self.client.post(create_url, {
            'name': 'Tomato',
            'kind': SeedEntry.Kind.HAVE,
            'offer_type': SeedEntry.OfferType.FREE,
            'quantity': 20,
            'unit': 'seeds',
        })

        self.assertRedirects(response, self.url)
        entry = SeedEntry.objects.get()
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.name, 'Tomato')
        self.assertEqual(entry.offer_type, SeedEntry.OfferType.FREE)

    def test_authenticated_navigation_shows_profile_and_logout(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertContains(response, 'seed-user')
        self.assertContains(response, reverse('logout'))
        self.assertNotContains(response, 'Create account')

    def test_user_can_add_seed_they_have(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('seeds:create'), {
            'name': 'Tomato',
            'kind': SeedEntry.Kind.HAVE,
            'offer_type': SeedEntry.OfferType.FREE,
            'variety': 'Roma',
            'description': 'Open-pollinated seeds',
            'quantity': 20,
            'unit': 'seeds',
            'location': 'Cauayan',
        })

        self.assertRedirects(response, self.url)
        entry = SeedEntry.objects.get()
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.kind, SeedEntry.Kind.HAVE)
        self.assertEqual(entry.offer_type, SeedEntry.OfferType.FREE)
        self.assertEqual(entry.name, 'Tomato')

    def test_user_can_offer_seeds_for_sale(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('seeds:create'), {
            'name': 'Tomato',
            'kind': SeedEntry.Kind.HAVE,
            'offer_type': SeedEntry.OfferType.SALE,
            'price': '25.50',
            'quantity': 20,
            'unit': 'seeds',
        })

        self.assertRedirects(response, self.url)
        entry = SeedEntry.objects.get()
        self.assertEqual(entry.offer_type, SeedEntry.OfferType.SALE)
        self.assertEqual(str(entry.price), '25.50')
        self.assertContains(self.client.get(self.url), 'For sale: 25.50')

    def test_sale_requires_a_price(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('seeds:create'), {
            'name': 'Tomato',
            'kind': SeedEntry.Kind.HAVE,
            'offer_type': SeedEntry.OfferType.SALE,
            'quantity': 20,
            'unit': 'seeds',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a price for seeds offered for sale.')
        self.assertFalse(SeedEntry.objects.exists())

    def test_user_can_offer_seeds_for_trade(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('seeds:create'), {
            'name': 'Tomato',
            'kind': SeedEntry.Kind.HAVE,
            'offer_type': SeedEntry.OfferType.TRADE,
            'trade_for': 'Pepper seeds',
            'quantity': 20,
            'unit': 'seeds',
        })

        self.assertRedirects(response, self.url)
        entry = SeedEntry.objects.get()
        self.assertEqual(entry.offer_type, SeedEntry.OfferType.TRADE)
        self.assertEqual(entry.trade_for, 'Pepper seeds')
        self.assertContains(self.client.get(self.url), 'Trade for: Pepper seeds')

    def test_trade_requires_requested_seed_details(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('seeds:create'), {
            'name': 'Tomato',
            'kind': SeedEntry.Kind.HAVE,
            'offer_type': SeedEntry.OfferType.TRADE,
            'quantity': 20,
            'unit': 'seeds',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Describe what you would like in exchange.')
        self.assertFalse(SeedEntry.objects.exists())

    def test_user_must_choose_offer_for_seeds_they_have(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('seeds:create'), {
            'name': 'Tomato',
            'kind': SeedEntry.Kind.HAVE,
            'quantity': 20,
            'unit': 'seeds',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Choose sale, free, or trade for a seed you have.')
        self.assertFalse(SeedEntry.objects.exists())

    def test_invalid_quantity_does_not_create_seed(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('seeds:create'), {
            'name': 'Tomato',
            'kind': SeedEntry.Kind.WANT,
            'offer_type': SeedEntry.OfferType.SALE,
            'price': '25.50',
            'trade_for': 'Pepper seeds',
            'quantity': 0,
            'unit': 'seeds',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SeedEntry.objects.exists())

    def test_want_post_does_not_save_offer_details(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('seeds:create'), {
            'name': 'Pepper',
            'kind': SeedEntry.Kind.WANT,
            'offer_type': SeedEntry.OfferType.SALE,
            'price': '25.50',
            'trade_for': 'Tomato seeds',
            'quantity': 10,
            'unit': 'seeds',
        })

        self.assertRedirects(response, self.url)
        entry = SeedEntry.objects.get()
        self.assertEqual(entry.kind, SeedEntry.Kind.WANT)
        self.assertEqual(entry.offer_type, '')
        self.assertIsNone(entry.price)
        self.assertEqual(entry.trade_for, '')


class MySeedPostsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username='owner', password='test-password-123')
        self.other_user = user_model.objects.create_user(username='other-user', password='test-password-123')
        self.entry = SeedEntry.objects.create(
            user=self.owner,
            name='Tomato',
            kind=SeedEntry.Kind.HAVE,
            offer_type=SeedEntry.OfferType.FREE,
            quantity=20,
            unit='seeds',
        )
        self.my_posts_url = reverse('seeds:my_posts')

    def test_my_posts_requires_login(self):
        response = self.client.get(self.my_posts_url)

        self.assertRedirects(response, f'{reverse("login")}?next={self.my_posts_url}')

    def test_my_posts_only_shows_current_users_entries(self):
        other_entry = SeedEntry.objects.create(
            user=self.other_user,
            name='Pepper',
            kind=SeedEntry.Kind.WANT,
            quantity=5,
            unit='seeds',
        )
        self.client.force_login(self.owner)

        response = self.client.get(self.my_posts_url)

        self.assertContains(response, self.entry.name)
        self.assertNotContains(response, other_entry.name)
        self.assertContains(response, reverse('seeds:edit', args=[self.entry.pk]))
        self.assertContains(response, reverse('seeds:delete', args=[self.entry.pk]))

    def test_authenticated_navigation_links_to_my_posts(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse('seeds:list'))

        self.assertContains(response, reverse('seeds:my_posts'))
        self.assertContains(response, 'My posts')

    def test_guest_navigation_does_not_show_my_posts(self):
        response = self.client.get(reverse('seeds:list'))

        self.assertNotContains(response, 'My posts')

    def test_owner_can_edit_their_post(self):
        self.client.force_login(self.owner)
        edit_url = reverse('seeds:edit', args=[self.entry.pk])

        page_response = self.client.get(edit_url)
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, 'Edit a post')

        response = self.client.post(edit_url, {
            'name': 'Roma Tomato',
            'kind': SeedEntry.Kind.HAVE,
            'offer_type': SeedEntry.OfferType.TRADE,
            'trade_for': 'Pepper seeds',
            'quantity': 12,
            'unit': 'packets',
            'description': 'Updated description',
        })

        self.assertRedirects(response, self.my_posts_url)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.user, self.owner)
        self.assertEqual(self.entry.name, 'Roma Tomato')
        self.assertEqual(self.entry.offer_type, SeedEntry.OfferType.TRADE)
        self.assertEqual(self.entry.trade_for, 'Pepper seeds')

    def test_user_cannot_edit_another_users_post(self):
        self.client.force_login(self.other_user)
        edit_url = reverse('seeds:edit', args=[self.entry.pk])

        response = self.client.get(edit_url)

        self.assertEqual(response.status_code, 404)

    def test_owner_can_delete_their_post(self):
        self.client.force_login(self.owner)

        response = self.client.post(reverse('seeds:delete', args=[self.entry.pk]))

        self.assertRedirects(response, self.my_posts_url)
        self.assertFalse(SeedEntry.objects.filter(pk=self.entry.pk).exists())

    def test_user_cannot_delete_another_users_post(self):
        self.client.force_login(self.other_user)

        response = self.client.post(reverse('seeds:delete', args=[self.entry.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(SeedEntry.objects.filter(pk=self.entry.pk).exists())

    def test_delete_requires_post_request(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse('seeds:delete', args=[self.entry.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(SeedEntry.objects.filter(pk=self.entry.pk).exists())


class SeedOrderTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.seller = user_model.objects.create_user(username='seller', password='test-password-123')
        self.buyer = user_model.objects.create_user(username='buyer', password='test-password-123')
        self.other_user = user_model.objects.create_user(username='other', password='test-password-123')
        self.entry = SeedEntry.objects.create(
            user=self.seller,
            name='Roma Tomato',
            kind=SeedEntry.Kind.HAVE,
            offer_type=SeedEntry.OfferType.SALE,
            price=Decimal('25.50'),
            quantity=20,
            unit='packets',
        )
        self.detail_url = reverse('seeds:detail', args=[self.entry.pk])
        self.order_url = reverse('seeds:order', args=[self.entry.pk])
        self.orders_url = reverse('seeds:orders')

    def submit_order(self, quantity=5, address='12 Garden Road, Cauayan'):
        return self.client.post(self.order_url, {
            'quantity': quantity,
            'delivery_address': address,
        })

    def create_order(self, buyer=None, quantity=5):
        return SeedOrder.objects.create(
            entry=self.entry,
            buyer=buyer or self.buyer,
            quantity=quantity,
            delivery_address='12 Garden Road, Cauayan',
            total_price=self.entry.price_for_quantity(quantity),
        )

    def test_only_signed_in_non_owner_can_order_sale_posts(self):
        guest_response = self.client.get(self.detail_url)
        self.assertContains(guest_response, reverse('login'))
        self.assertContains(guest_response, 'Sign in to order')

        self.client.force_login(self.seller)
        seller_response = self.client.get(self.detail_url)
        self.assertNotContains(seller_response, self.order_url)
        self.assertEqual(self.client.get(self.order_url).status_code, 404)

        self.client.force_login(self.buyer)
        buyer_response = self.client.get(self.detail_url)
        self.assertContains(buyer_response, self.order_url)
        self.assertEqual(self.client.get(self.order_url).status_code, 200)

    def test_order_request_saves_prorated_total_and_private_address(self):
        self.client.force_login(self.buyer)
        address = 'Private delivery: 42 Garden Lane'

        response = self.submit_order(quantity=5, address=address)

        self.assertRedirects(response, self.orders_url)
        order = SeedOrder.objects.get()
        self.assertEqual(order.status, SeedOrder.Status.PENDING)
        self.assertEqual(order.total_price, Decimal('6.38'))
        self.assertEqual(order.delivery_address, address)

        public_detail = self.client.get(self.detail_url)
        self.assertNotContains(public_detail, address)
        self.client.force_login(self.other_user)
        unrelated_orders = self.client.get(self.orders_url)
        self.assertNotContains(unrelated_orders, address)

        self.client.force_login(self.seller)
        seller_orders = self.client.get(self.orders_url)
        self.assertContains(seller_orders, address)
        self.assertContains(seller_orders, '1 pending request')
        self.client.force_login(self.buyer)
        buyer_orders = self.client.get(self.orders_url)
        self.assertContains(buyer_orders, address)
        self.assertContains(buyer_orders, 'Pending')

    def test_invalid_quantity_or_address_does_not_create_order(self):
        self.client.force_login(self.buyer)

        response = self.submit_order(quantity=21)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Only 20 packets are currently available.')

        response = self.submit_order(quantity=0)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ensure this value is greater than or equal to 1.')

        response = self.submit_order(quantity=2, address='   ')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a delivery address.')
        self.assertFalse(SeedOrder.objects.exists())

    def test_cannot_order_own_non_sale_or_missing_listing(self):
        self.client.force_login(self.buyer)
        free_entry = SeedEntry.objects.create(
            user=self.seller,
            name='Free seeds',
            kind=SeedEntry.Kind.HAVE,
            offer_type=SeedEntry.OfferType.FREE,
        )
        want_entry = SeedEntry.objects.create(
            user=self.seller,
            name='Wanted seeds',
            kind=SeedEntry.Kind.WANT,
        )

        self.assertEqual(self.client.get(reverse('seeds:order', args=[free_entry.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('seeds:order', args=[want_entry.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('seeds:order', args=[99999])).status_code, 404)

    def test_accepting_order_updates_available_stock_and_buyer_status(self):
        order = self.create_order(quantity=5)
        self.client.force_login(self.seller)

        response = self.client.post(reverse('seeds:order_action', args=[order.pk, 'accept']))

        self.assertRedirects(response, self.orders_url)
        order.refresh_from_db()
        self.assertEqual(order.status, SeedOrder.Status.ACCEPTED)
        detail_response = self.client.get(self.detail_url)
        self.assertEqual(detail_response.context['entry'].available_quantity, 15)
        self.assertContains(detail_response, 'available')
        self.assertNotContains(detail_response, 'Order seeds')

        self.client.force_login(self.buyer)
        self.assertContains(self.client.get(self.orders_url), 'Accepted')
        self.assertNotContains(self.client.get(self.detail_url), 'Private delivery')

    def test_rejecting_order_does_not_reduce_available_stock(self):
        order = self.create_order(quantity=5)
        self.client.force_login(self.seller)

        response = self.client.post(reverse('seeds:order_action', args=[order.pk, 'reject']))

        self.assertRedirects(response, self.orders_url)
        order.refresh_from_db()
        self.assertEqual(order.status, SeedOrder.Status.REJECTED)
        self.assertEqual(self.client.get(self.detail_url).context['entry'].available_quantity, 20)

    def test_pending_orders_do_not_reserve_stock_and_acceptance_prevents_overselling(self):
        first_order = self.create_order(quantity=15)
        second_order = self.create_order(quantity=10)
        self.client.force_login(self.seller)

        self.client.post(reverse('seeds:order_action', args=[first_order.pk, 'accept']))
        response = self.client.post(
            reverse('seeds:order_action', args=[second_order.pk, 'accept']),
            follow=True,
        )

        first_order.refresh_from_db()
        second_order.refresh_from_db()
        self.assertEqual(first_order.status, SeedOrder.Status.ACCEPTED)
        self.assertEqual(second_order.status, SeedOrder.Status.PENDING)
        self.assertContains(response, 'There is not enough stock to accept this order.')
        self.assertEqual(self.client.get(self.detail_url).context['entry'].available_quantity, 5)

    def test_only_seller_can_process_pending_order_and_actions_require_post(self):
        order = self.create_order()
        action_url = reverse('seeds:order_action', args=[order.pk, 'accept'])

        self.client.force_login(self.buyer)
        self.assertEqual(self.client.post(action_url).status_code, 404)

        self.client.force_login(self.seller)
        self.assertEqual(self.client.get(action_url).status_code, 405)
        order.refresh_from_db()
        self.assertEqual(order.status, SeedOrder.Status.PENDING)

    def test_cannot_delete_or_reduce_listing_below_accepted_orders(self):
        order = self.create_order(quantity=5)
        order.status = SeedOrder.Status.ACCEPTED
        order.save(update_fields=['status'])
        self.client.force_login(self.seller)

        edit_response = self.client.post(reverse('seeds:edit', args=[self.entry.pk]), {
            'name': self.entry.name,
            'kind': self.entry.kind,
            'offer_type': self.entry.offer_type,
            'price': self.entry.price,
            'quantity': 4,
            'unit': self.entry.unit,
        })
        self.assertEqual(edit_response.status_code, 200)
        self.assertContains(edit_response, 'Quantity cannot be lower than the 5 packets already sold or traded.')

        delete_response = self.client.post(
            reverse('seeds:delete', args=[self.entry.pk]),
            follow=True,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(SeedEntry.objects.filter(pk=self.entry.pk).exists())
        self.assertContains(delete_response, 'cannot be deleted because it has transaction history')


class SeedRatingAndTradeTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username='post-owner', password='test-password-123')
        self.requester = user_model.objects.create_user(username='requester', password='test-password-123')
        self.other_user = user_model.objects.create_user(username='visitor', password='test-password-123')
        self.sale_entry = SeedEntry.objects.create(
            user=self.owner,
            name='Sale tomato seeds',
            kind=SeedEntry.Kind.HAVE,
            offer_type=SeedEntry.OfferType.SALE,
            price=Decimal('12.00'),
            quantity=12,
            unit='packets',
        )
        self.sale_detail_url = reverse('seeds:detail', args=[self.sale_entry.pk])
        self.orders_url = reverse('seeds:orders')

    def create_completed_order(self):
        order = SeedOrder.objects.create(
            entry=self.sale_entry,
            buyer=self.requester,
            quantity=3,
            delivery_address='Private address',
            total_price=self.sale_entry.price_for_quantity(3),
            status=SeedOrder.Status.COMPLETED,
            buyer_confirmed_completion=True,
            seller_confirmed_completion=True,
        )
        return order

    def test_posts_show_rating_summary_even_without_ratings(self):
        self.client.force_login(self.other_user)

        sale_detail = self.client.get(self.sale_detail_url)
        self.assertContains(sale_detail, 'This post has not been rated yet.')
        self.assertFalse(sale_detail.context['can_rate'])

        want_entry = SeedEntry.objects.create(
            user=self.owner,
            name='Wanted pepper seeds',
            kind=SeedEntry.Kind.WANT,
            quantity=4,
        )
        want_detail = self.client.get(reverse('seeds:detail', args=[want_entry.pk]))
        self.assertContains(want_detail, 'This post has not been rated yet.')

    def test_only_completed_participants_can_rate_and_can_update_one_rating(self):
        self.client.force_login(self.other_user)
        response = self.client.post(reverse('seeds:rate', args=[self.sale_entry.pk]), {'score': '5'}, follow=True)
        self.assertContains(response, 'Only participants in a completed order or trade can rate this post.')
        self.assertFalse(SeedRating.objects.exists())

        self.create_completed_order()
        self.client.force_login(self.requester)
        detail = self.client.get(self.sale_detail_url)
        self.assertTrue(detail.context['can_rate'])
        self.assertContains(detail, 'Rate this post')

        self.client.post(reverse('seeds:rate', args=[self.sale_entry.pk]), {'score': '4'})
        self.client.post(reverse('seeds:rate', args=[self.sale_entry.pk]), {'score': '5'})
        self.assertEqual(SeedRating.objects.filter(entry=self.sale_entry, user=self.requester).count(), 1)

        detail = self.client.get(self.sale_detail_url)
        self.assertContains(detail, '5.0 / 5')
        self.assertContains(detail, '(1 rating)')
        self.assertEqual(detail.context['entry'].rating_average, 5)

        self.client.force_login(self.owner)
        owner_detail = self.client.get(self.sale_detail_url)
        self.assertTrue(owner_detail.context['can_rate'])
        self.client.post(reverse('seeds:rate', args=[self.sale_entry.pk]), {'score': '3'})
        detail = self.client.get(self.sale_detail_url)
        self.assertEqual(detail.context['entry'].rating_count, 2)
        self.assertEqual(detail.context['entry'].rating_average, 4)

    def test_sale_requires_both_participants_to_confirm_before_rating(self):
        self.client.force_login(self.requester)
        self.client.post(reverse('seeds:order', args=[self.sale_entry.pk]), {
            'quantity': 2,
            'delivery_address': '12 Garden Road',
        })
        order = SeedOrder.objects.get()

        self.client.force_login(self.owner)
        self.client.post(reverse('seeds:order_action', args=[order.pk, 'accept']))
        self.client.post(reverse('seeds:order_complete', args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.status, SeedOrder.Status.ACCEPTED)
        self.assertTrue(order.seller_confirmed_completion)

        self.client.force_login(self.requester)
        detail_before_confirm = self.client.get(self.sale_detail_url)
        self.assertFalse(detail_before_confirm.context['can_rate'])
        self.client.post(reverse('seeds:order_complete', args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.status, SeedOrder.Status.COMPLETED)

        detail_after_confirm = self.client.get(self.sale_detail_url)
        self.assertTrue(detail_after_confirm.context['can_rate'])
        self.assertEqual(detail_after_confirm.context['entry'].available_quantity, 10)

    def test_trade_request_on_want_post_requires_acceptance_and_both_completion_confirmations(self):
        want_entry = SeedEntry.objects.create(
            user=self.owner,
            name='Wanted pepper seeds',
            kind=SeedEntry.Kind.WANT,
            description='Looking for sweet pepper seeds.',
            quantity=10,
            unit='packets',
        )
        detail_url = reverse('seeds:detail', args=[want_entry.pk])
        trade_url = reverse('seeds:trade_request', args=[want_entry.pk])
        self.client.force_login(self.requester)

        self.assertContains(self.client.get(detail_url), 'Request a trade')
        response = self.client.post(trade_url, {
            'quantity': 4,
            'offer_description': 'Four basil seed packets.',
        })
        self.assertRedirects(response, self.orders_url)
        trade = SeedTradeRequest.objects.get()
        self.assertEqual(trade.status, SeedTradeRequest.Status.PENDING)

        self.client.force_login(self.owner)
        self.client.post(reverse('seeds:trade_action', args=[trade.pk, 'accept']))
        trade.refresh_from_db()
        self.assertEqual(trade.status, SeedTradeRequest.Status.ACCEPTED)
        self.client.post(reverse('seeds:trade_action', args=[trade.pk, 'complete']))
        trade.refresh_from_db()
        self.assertTrue(trade.owner_confirmed_completion)

        self.client.force_login(self.requester)
        self.assertFalse(self.client.get(detail_url).context['can_rate'])
        self.client.post(reverse('seeds:trade_action', args=[trade.pk, 'complete']))
        trade.refresh_from_db()
        self.assertEqual(trade.status, SeedTradeRequest.Status.COMPLETED)
        self.assertTrue(trade.requester_confirmed_completion)

        self.assertEqual(self.client.get(detail_url).context['entry'].available_quantity, 6)
        self.assertTrue(self.client.get(detail_url).context['can_rate'])

        self.client.force_login(self.requester)
        self.assertTrue(self.client.get(detail_url).context['can_rate'])
        self.client.post(reverse('seeds:rate', args=[want_entry.pk]), {'score': '4'})
        self.assertEqual(SeedRating.objects.get(entry=want_entry, user=self.requester).score, 4)

    def test_trade_completion_checks_remaining_quantity(self):
        trade_entry = SeedEntry.objects.create(
            user=self.owner,
            name='Trade tomato seeds',
            kind=SeedEntry.Kind.HAVE,
            offer_type=SeedEntry.OfferType.TRADE,
            trade_for='Pepper seeds',
            quantity=5,
            unit='packets',
        )
        first = SeedTradeRequest.objects.create(
            entry=trade_entry,
            requester=self.requester,
            quantity=4,
            offer_description='Basil seeds',
            status=SeedTradeRequest.Status.ACCEPTED,
            requester_confirmed_completion=True,
        )
        second_user = get_user_model().objects.create_user(
            username='second-requester',
            password='test-password-123',
        )
        second = SeedTradeRequest.objects.create(
            entry=trade_entry,
            requester=second_user,
            quantity=4,
            offer_description='Lettuce seeds',
            status=SeedTradeRequest.Status.ACCEPTED,
            owner_confirmed_completion=True,
        )

        self.client.force_login(self.owner)
        self.client.post(reverse('seeds:trade_action', args=[first.pk, 'complete']))
        first.refresh_from_db()
        self.assertEqual(first.status, SeedTradeRequest.Status.COMPLETED)

        self.client.force_login(second_user)
        response = self.client.post(
            reverse('seeds:trade_action', args=[second.pk, 'complete']),
            follow=True,
        )
        second.refresh_from_db()
        self.assertEqual(second.status, SeedTradeRequest.Status.ACCEPTED)
        self.assertFalse(second.requester_confirmed_completion)
        self.assertContains(response, 'There is not enough quantity to complete this trade.')

    def test_trade_acceptance_is_owner_only_and_rating_score_is_bounded(self):
        trade_entry = SeedEntry.objects.create(
            user=self.owner,
            name='Trade seeds',
            kind=SeedEntry.Kind.HAVE,
            offer_type=SeedEntry.OfferType.TRADE,
            trade_for='Pepper seeds',
            quantity=5,
        )
        trade = SeedTradeRequest.objects.create(
            entry=trade_entry,
            requester=self.requester,
            quantity=1,
            offer_description='Basil seeds',
        )
        action_url = reverse('seeds:trade_action', args=[trade.pk, 'accept'])

        self.client.force_login(self.other_user)
        self.assertEqual(self.client.post(action_url).status_code, 404)

        self.create_completed_order()
        self.client.force_login(self.requester)
        response = self.client.post(
            reverse('seeds:rate', args=[self.sale_entry.pk]),
            {'score': '6'},
            follow=True,
        )
        self.assertContains(response, 'Choose a star rating from 1 to 5.')
        self.assertFalse(SeedRating.objects.filter(entry=self.sale_entry).exists())
