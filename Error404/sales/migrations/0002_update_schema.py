from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='price_large',
            field=models.DecimalField(decimal_places=2, default=0.0, help_text='Price for Large (Tax Inclusive)', max_digits=10),
        ),
        migrations.AddField(
            model_name='product',
            name='price_medium',
            field=models.DecimalField(decimal_places=2, default=0.0, help_text='Price for Medium (Tax Inclusive)', max_digits=10),
        ),
        migrations.AddField(
            model_name='product',
            name='price_small',
            field=models.DecimalField(decimal_places=2, default=0.0, help_text='Price for Small (Tax Inclusive)', max_digits=10),
        ),
        migrations.AddField(
            model_name='recipe',
            name='group_name',
            field=models.CharField(blank=True, help_text="Ingredients with the same group name will appear as a single choice (e.g., 'Milk Type')", max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='recipe',
            name='is_optional',
            field=models.BooleanField(default=False, help_text='Check if this is an optional add-on or a swap choice'),
        ),
        migrations.AlterField(
            model_name='product',
            name='category',
            field=models.CharField(choices=[('Coffee', 'Coffee'), ('Tea', 'Tea'), ('Soft Drink', 'Soft Drink'), ('Other', 'Other')], default='Coffee', max_length=20),
        ),
        migrations.AlterField(
            model_name='product',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='products/'),
        ),
    ]