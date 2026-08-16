from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.payments'
    verbose_name = 'Payments'

    def ready(self):
        # Wiring a rail only says it *can* hold an authorisation. Whether any
        # booking actually defers is the cooling-off scheme's decision, asked
        # per payment in should_defer_capture().
        from .capture import register_rails
        register_rails()
