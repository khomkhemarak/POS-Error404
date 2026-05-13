# Generated migration for daily order number reset

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0012_passwordresetotp'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='order_date',
            field=models.DateField(auto_now_add=True),
        ),
        migrations.AddField(
            model_name='order',
            name='order_number',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='order',
            name='order_date',
            field=models.DateField(auto_now_add=True),
        ),
    ]
