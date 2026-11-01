from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


def copy_seed_data(apps, schema_editor):
    SeedListing = apps.get_model('seeds', 'SeedListing')
    SeedRequest = apps.get_model('seeds', 'SeedRequest')
    SeedEntry = apps.get_model('seeds', 'SeedEntry')
    database = schema_editor.connection.alias

    entries = [
        SeedEntry(
            user_id=listing.owner_id,
            name=listing.title,
            kind='have',
            variety=listing.variety,
            description=listing.description,
            quantity=listing.quantity,
            unit=listing.unit,
            location=listing.location,
        )
        for listing in SeedListing.objects.using(database).all().iterator()
    ]

    requests = (
        SeedRequest.objects.using(database)
        .select_related('listing')
        .iterator()
    )
    entries.extend(
        SeedEntry(
            user_id=request.requester_id,
            name=request.listing.title,
            kind='want',
            quantity=request.quantity,
            request_status=request.status,
            message=request.message,
        )
        for request in requests
    )

    SeedEntry.objects.using(database).bulk_create(entries)


class Migration(migrations.Migration):

    dependencies = [
        ('seeds', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SeedEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('kind', models.CharField(choices=[('have', 'Have'), ('want', 'Want')], max_length=4)),
                ('variety', models.CharField(blank=True, max_length=120)),
                ('description', models.TextField(blank=True)),
                ('quantity', models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])),
                ('unit', models.CharField(default='seeds', max_length=40)),
                ('location', models.CharField(blank=True, max_length=255)),
                ('request_status', models.CharField(blank=True, choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected'), ('cancelled', 'Cancelled')], max_length=10)),
                ('message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='seed_entries', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.RunPython(copy_seed_data, migrations.RunPython.noop),
        migrations.DeleteModel(name='SeedRequest'),
        migrations.DeleteModel(name='SeedListing'),
    ]
