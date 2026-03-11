from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0005_passwordresettoken'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='puck_data',
            field=models.JSONField(blank=True, null=True, verbose_name='Données Puck Editor'),
        ),
        migrations.AddField(
            model_name='document',
            name='global_background',
            field=models.JSONField(blank=True, null=True, verbose_name='Background global Puck'),
        ),
        migrations.AddField(
            model_name='document',
            name='header_footer',
            field=models.JSONField(blank=True, null=True, verbose_name='Header/Footer Puck'),
        ),
    ]
