from decimal import Decimal

from django import forms

from .models import SeedEntry, SeedImage, SeedRating


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        return [super().clean(image, initial) for image in data]


class SeedEntryForm(forms.ModelForm):
    MAX_IMAGES = 3
    MAX_IMAGE_SIZE = 5 * 1024 * 1024

    upload_images = MultipleImageField(
        required=False,
        label='Seed photos',
        help_text='Upload up to 3 JPG, PNG, or WebP images, up to 5 MB each.',
    )
    remove_images = forms.ModelMultipleChoiceField(
        queryset=SeedImage.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Remove current photos',
    )

    class Meta:
        model = SeedEntry
        fields = [
            'name',
            'kind',
            'offer_type',
            'price',
            'trade_for',
            'variety',
            'description',
            'quantity',
            'unit',
            'location',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'kind': forms.Select(attrs={'class': 'form-select'}),
            'offer_type': forms.Select(attrs={
                'class': 'form-select',
                'data-offer-type': '',
            }),
            'price': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '0.01',
                'data-offer-price': '',
            }),
            'trade_for': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'data-offer-trade': '',
            }),
            'variety': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'offer_type': 'How are you offering these seeds?',
            'price': 'Price (in your local currency)',
            'trade_for': 'What would you like in exchange?',
        }
        help_texts = {
            'price': 'Price for the full quantity in this post.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['remove_images'].queryset = self.instance.images.all()
        self.fields['upload_images'].widget.attrs.update({
            'class': 'form-control',
            'accept': '.jpg,.jpeg,.png,.webp',
        })

    def clean(self):
        cleaned_data = super().clean()
        kind = cleaned_data.get('kind')
        offer_type = cleaned_data.get('offer_type')
        upload_images = cleaned_data.get('upload_images', [])
        remove_images = cleaned_data.get('remove_images', [])

        for image in upload_images:
            if image.size > self.MAX_IMAGE_SIZE:
                self.add_error('upload_images', f'Each image must be 5 MB or smaller: {image.name}')

        current_image_count = self.instance.images.count() if self.instance.pk else 0
        remaining_image_count = current_image_count - len(remove_images)
        if remaining_image_count + len(upload_images) > self.MAX_IMAGES:
            self.add_error(
                'upload_images',
                f'A post can have up to {self.MAX_IMAGES} photos. Remove a current photo or select fewer images.',
            )

        if kind != SeedEntry.Kind.HAVE:
            cleaned_data['offer_type'] = ''
            cleaned_data['price'] = None
            cleaned_data['trade_for'] = ''
            return cleaned_data

        if not offer_type:
            self.add_error('offer_type', 'Choose sale, free, or trade for a seed you have.')
        elif offer_type == SeedEntry.OfferType.SALE:
            if cleaned_data.get('price') is None:
                self.add_error('price', 'Enter a price for seeds offered for sale.')
            cleaned_data['trade_for'] = ''
        elif offer_type == SeedEntry.OfferType.FREE:
            cleaned_data['price'] = None
            cleaned_data['trade_for'] = ''
        elif offer_type == SeedEntry.OfferType.TRADE:
            cleaned_data['price'] = None
            if not cleaned_data.get('trade_for', '').strip():
                self.add_error('trade_for', 'Describe what you would like in exchange.')
        return cleaned_data

    def save_images(self, entry):
        for image in self.cleaned_data['remove_images']:
            image.delete()
        for image in self.cleaned_data['upload_images']:
            SeedImage.objects.create(entry=entry, image=image)


class SeedOrderForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 1,
        }),
    )
    delivery_address = forms.CharField(
        max_length=1000,
        strip=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
        }),
    )

    def __init__(self, *args, entry, available_quantity, **kwargs):
        super().__init__(*args, **kwargs)
        self.entry = entry
        self.available_quantity = available_quantity
        self.fields['quantity'].widget.attrs['max'] = available_quantity

    def clean_quantity(self):
        quantity = self.cleaned_data['quantity']
        if quantity > self.available_quantity:
            raise forms.ValidationError(
                f'Only {self.available_quantity} {self.entry.unit} are currently available.'
            )
        if self.entry.price_for_quantity(quantity) < Decimal('0.01'):
            raise forms.ValidationError(
                'Choose a larger quantity so the prorated total is at least 0.01.'
            )
        return quantity

    def clean_delivery_address(self):
        address = self.cleaned_data['delivery_address'].strip()
        if not address:
            raise forms.ValidationError('Enter a delivery address.')
        return address


class SeedTradeRequestForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 1,
        }),
    )
    offer_description = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Describe the seeds or items you can offer in exchange.',
        }),
    )

    def __init__(self, *args, entry, available_quantity, **kwargs):
        super().__init__(*args, **kwargs)
        self.entry = entry
        self.available_quantity = available_quantity
        self.fields['quantity'].widget.attrs['max'] = available_quantity

    def clean_quantity(self):
        quantity = self.cleaned_data['quantity']
        if quantity > self.available_quantity:
            raise forms.ValidationError(
                f'Only {self.available_quantity} {self.entry.unit} are currently available.'
            )
        return quantity

    def clean_offer_description(self):
        description = self.cleaned_data['offer_description'].strip()
        if not description:
            raise forms.ValidationError('Describe what you are offering in exchange.')
        return description


class SeedRatingForm(forms.ModelForm):
    score = forms.ChoiceField(
        choices=[(value, f'{value} star{"s" if value != 1 else ""}') for value in range(1, 6)],
        widget=forms.RadioSelect,
        label='Your rating',
    )

    class Meta:
        model = SeedRating
        fields = ['score']
