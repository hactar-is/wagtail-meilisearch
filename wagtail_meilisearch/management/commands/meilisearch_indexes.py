import arrow
from wagtail.search.backends import get_search_backend
from django.core.management.base import BaseCommand


SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


def human_readable_file_size(size_in_bytes):
    index = 0
    while size_in_bytes >= 1024:
        size_in_bytes /= 1024
        index += 1
    try:
        rounded = '{0:.3f}'.format(size_in_bytes)
        return f'{rounded} {SIZE_UNITS[index]}'
    except IndexError:
        return 'Index too large'


class Command(BaseCommand):

    """This is some of the ugliest code I've ever written, I'm sorry.
    """

    help = "Display info about each Meilisearch index"

    def handle(self, *args, **options):
        b = get_search_backend()
        stats = b.client.get_all_stats()
        print(stats)
        indexes = stats['indexes']
        print("*" * 80)
        print(f"Total DB size: {human_readable_file_size(stats['databaseSize'])}")
        print(f"Last updated: {arrow.get(stats['lastUpdate']).format('YYYY-MM-DD HH:mm:ss')}")
        if not len(indexes):
            print('No indexes created yet')
        else:
            print("Indexes:")
            for k, v in indexes.items():
                is_indexing = v['isIndexing']
                index = b.client.get_index(k)
                settings = index.get_settings()
                settings.pop('stopWords')
                print(f"{k} - indexing: {is_indexing}")
                print(f"\t displayedAttributes: {settings.get('displayedAttributes')}")
                print(f"\t searchableAttributes: {settings.get('searchableAttributes')}")
                print(f"\t filterableAttributes: {settings.get('filterableAttributes')}")
                print(f"\t sortableAttributes: {settings.get('sortableAttributes')}")
                print(f"\t rankingRules: {settings.get('rankingRuless')}")
                print(f"\t synonyms: {settings.get('synonyms')}")
                print(f"\t distinctAttribute: {settings.get('distinctAttribute')}")
                print(f"\t typoTolerance: {settings.get('typoTolerance')}")
                print(f"\t faceting: {settings.get('faceting')}")
                print(f"\t pagination: {settings.get('pagination')}")

                print('\n')
                print("*" * 80)

    def _print_index_stats(self, model, v):
        print(f"{model}")
        print(f"  Documents: {v['numberOfDocuments']}")
        if v['isIndexing'] is True:
            print('  INDEXING')
        print("")
