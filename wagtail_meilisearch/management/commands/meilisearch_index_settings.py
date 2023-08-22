import arrow
from wagtail.search.backends import get_search_backend
from django.core.management.base import BaseCommand


class Command(BaseCommand):

    """Apply updated settings to every index
    """

    help = "Apply updated settings to every index"

    def handle(self, *args, **options):
        b = get_search_backend()
        res =  b.client.get_indexes(parameters={'limit': 999999})
        indexes = res.get('results', [])
        for index in indexes:
            capt = index.update_settings(
                {
                    'stopWords': b.stop_words,
                    'rankingRules': b.ranking_rules,
                },
            )
            print(capt)
