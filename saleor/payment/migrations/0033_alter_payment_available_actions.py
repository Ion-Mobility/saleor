# Generated by Django 3.2.12 on 2022-03-16 10:57

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payment", "0032_auto_20220315_1136"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="available_actions",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(
                    choices=[
                        ("capture", "Capture payment"),
                        ("refund", "Refund payment"),
                        ("void", "Void payment"),
                        ("mark_as_paid", "Mark as paid"),
                    ],
                    max_length=128,
                ),
                default=list,
                size=None,
            ),
        ),
    ]