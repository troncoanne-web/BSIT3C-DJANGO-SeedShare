from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver


def seed_image_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f'seed_images/{instance.entry_id}/{uuid4().hex}{extension}'


class SeedEntry(models.Model):
    class Kind(models.TextChoices):
        HAVE = 'have', 'Have'
        WANT = 'want', 'Want'

    class OfferType(models.TextChoices):
        SALE = 'sale', 'For sale'
        FREE = 'free', 'Free'
        TRADE = 'trade', 'Trade'

    class RequestStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'
        CANCELLED = 'cancelled', 'Cancelled'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='seed_entries',
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=4, choices=Kind.choices)
    offer_type = models.CharField(
        max_length=5,
        choices=OfferType.choices,
        blank=True,
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0.01)],
    )
    trade_for = models.TextField(blank=True)
    variety = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    unit = models.CharField(max_length=40, default='seeds')
    location = models.CharField(max_length=255, blank=True)
    request_status = models.CharField(
        max_length=10,
        choices=RequestStatus.choices,
        blank=True,
    )
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.get_kind_display()})'

    def price_for_quantity(self, quantity):
        if self.price is None:
            raise ValueError('A sale price is required to calculate an order total.')
        return (Decimal(self.price) * quantity / self.quantity).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP,
        )


class SeedImage(models.Model):
    entry = models.ForeignKey(
        SeedEntry,
        related_name='images',
        on_delete=models.CASCADE,
    )
    image = models.ImageField(
        upload_to=seed_image_upload_path,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'Image for {self.entry.name}'


@receiver(post_delete, sender=SeedImage)
def delete_seed_image_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)


class SeedOrder(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'
        COMPLETED = 'completed', 'Completed'

    entry = models.ForeignKey(
        SeedEntry,
        related_name='orders',
        on_delete=models.PROTECT,
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='seed_orders',
        on_delete=models.PROTECT,
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    delivery_address = models.TextField(max_length=1000)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    buyer_confirmed_completion = models.BooleanField(default=False)
    seller_confirmed_completion = models.BooleanField(default=False)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Order for {self.entry.name} by {self.buyer.username}'


class SeedTradeRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'
        COMPLETED = 'completed', 'Completed'

    entry = models.ForeignKey(
        SeedEntry,
        related_name='trade_requests',
        on_delete=models.PROTECT,
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='seed_trade_requests',
        on_delete=models.PROTECT,
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    offer_description = models.TextField(max_length=1000)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    requester_confirmed_completion = models.BooleanField(default=False)
    owner_confirmed_completion = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Trade request for {self.entry.name} by {self.requester.username}'


class SeedRating(models.Model):
    entry = models.ForeignKey(
        SeedEntry,
        related_name='ratings',
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='seed_ratings',
        on_delete=models.CASCADE,
    )
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['entry', 'user'],
                name='unique_seed_rating_per_user',
            ),
            models.CheckConstraint(
                check=models.Q(score__gte=1, score__lte=5),
                name='seed_rating_score_1_to_5',
            ),
        ]

    def __str__(self):
        return f'{self.score}/5 rating for {self.entry.name}'
