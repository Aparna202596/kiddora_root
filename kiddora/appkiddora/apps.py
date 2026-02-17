from django.apps import AppConfig

class OrdersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'appkiddora'

    def ready(self):
        import appkiddora.signals
