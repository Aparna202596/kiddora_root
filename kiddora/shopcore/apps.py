from django.apps import AppConfig


class ShopcoreConfig(AppConfig):

    name = "shopcore"

    def ready(self):
        import shopcore.signals
