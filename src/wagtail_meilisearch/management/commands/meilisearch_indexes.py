from typing import Dict, List, Union

import arrow
from django.core.management.base import BaseCommand
from wagtail.search.backends import get_search_backend

SIZE_UNITS: List[str] = ["B", "KB", "MB", "GB", "TB", "PB"]


def human_readable_file_size(size_in_bytes: float) -> str:
    """Convert a size in bytes to a human-readable string.

    Args:
        size_in_bytes: The size in bytes to convert.

    Returns:
        str: A human-readable representation of the size with appropriate unit suffix.
            Returns 'Index too large' if the size exceeds the available units.
    """
    index = 0
    while size_in_bytes >= 1024:
        size_in_bytes /= 1024
        index += 1
    try:
        rounded = "{0:.3f}".format(size_in_bytes)
        return f"{rounded} {SIZE_UNITS[index]}"
    except IndexError:
        return "Index too large"


class Command(BaseCommand):
    """Command to display detailed information about each MeiliSearch index.

    This command retrieves and displays comprehensive settings and statistics
    for all MeiliSearch indexes in the system.
    """

    help = "Display info about each Meilisearch index"

    def handle(self, *_args, **_kwargs) -> None:
        """Execute the command to display index information.

        Django passes arguments to this method, but we don't use them.
        The underscore prefix indicates these arguments are intentionally unused.
        """
        b = get_search_backend()
        stats: Dict[str, Union[float, str, Dict]] = b.client.get_all_stats()
        print(stats)
        indexes: Dict[str, Dict] = stats["indexes"]
        print("*" * 80)
        print(f"Total DB size: {human_readable_file_size(stats['databaseSize'])}")
        print(f"Last updated: {arrow.get(stats['lastUpdate']).format('YYYY-MM-DD HH:mm:ss')}")
        if not len(indexes):
            print("No indexes created yet")
        else:
            print("Indexes:")
            for k, v in indexes.items():
                is_indexing = v["isIndexing"]
                index = b.client.get_index(k)
                settings = index.get_settings()
                settings.pop("stopWords")
                print(f"{k} - indexing: {is_indexing}")
                print(f"\t displayedAttributes: {settings.get('displayedAttributes')}")
                print(f"\t searchableAttributes: {settings.get('searchableAttributes')}")
                print(f"\t filterableAttributes: {settings.get('filterableAttributes')}")
                print(f"\t sortableAttributes: {settings.get('sortableAttributes')}")
                print(f"\t rankingRules: {settings.get('rankingRules')}")
                print(f"\t synonyms: {settings.get('synonyms')}")
                print(f"\t distinctAttribute: {settings.get('distinctAttribute')}")
                print(f"\t typoTolerance: {settings.get('typoTolerance')}")
                print(f"\t faceting: {settings.get('faceting')}")
                print(f"\t pagination: {settings.get('pagination')}")

                print("\n")
                print("*" * 80)
