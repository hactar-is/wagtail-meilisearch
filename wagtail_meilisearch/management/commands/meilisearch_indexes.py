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
        import ipdb; ipdb.set_trace()
        indexes = stats['indexes']
        print("*" * 80)
        print(f"Index DB size: {human_readable_file_size(stats['databaseSize'])}")
        print(f"Last updated: {arrow.get(stats['lastUpdate']).format('YYYY-MM-DD HH:mm:ss')}")
        if not len(indexes):
            print('No indexes created yet')
        else:
            print("Indexes:")
            for k, v in indexes.items():
                model = k.replace('-', '.')
                is_indexing = v['isIndexing']
                if len(models):
                    if model in models:
                        if indexing:
                            if is_indexing:
                                self._print_index_stats(model, v)
                        else:
                            self._print_index_stats(model, v)
                else:
                    if indexing:
                        if is_indexing:
                            self._print_index_stats(model, v)
                    else:
                        self._print_index_stats(model, v)

        print("*" * 80)

    def _print_index_stats(self, model, v):
        print(f"{model}")
        print(f"  Documents: {v['numberOfDocuments']}")
        if v['isIndexing'] is True:
            print('  INDEXING')
        print("")
