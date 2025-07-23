from typing import Dict, List, Optional, Union

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
    """Command to display status information about MeiliSearch indexes.

    This command provides statistics about the MeiliSearch backend,
    including database size, last update time, and details about each index.
    """

    help = "Print some stats about the meilisearch backend"

    def add_arguments(self, parser) -> None:
        """Add command line arguments.

        Args:
            parser: The argument parser to which arguments should be added.
        """
        # Named (optional) arguments
        parser.add_argument(
            "--indexing",
            action="store_true",
            help="Show only models that MeiliSearch is currently indexing",
        )
        parser.add_argument(
            "--models",
            type=str,
            help="Show only models in this comma separated list of model labels",
        )

    def handle(self, **options) -> None:
        """Execute the command.

        Args:
            **options: Command options including 'models' and 'indexing'.
        """
        models: List[str] = []
        models_string: Optional[str] = options.get("models", "")
        if models_string:
            models = models_string.split(",")
        indexing: bool = options.get("indexing", False)

        # Get MeiliSearch backend and stats
        b = get_search_backend()
        stats: Dict[str, Union[float, str, Dict]] = b.client.get_all_stats()
        indexes: Dict[str, Dict] = stats["indexes"]

        print("*" * 80)
        print(f"Index DB size: {human_readable_file_size(stats['databaseSize'])}")
        print(f"Last updated: {arrow.get(stats['lastUpdate']).format('YYYY-MM-DD HH:mm:ss')}")

        if not len(indexes):
            print("No indexes created yet")
        else:
            print("Indexes:")
            for k, v in indexes.items():
                model = k.replace("-", ".")
                is_indexing = v["isIndexing"]

                # Filter by model name if models list is provided
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

    def _print_index_stats(self, model: str, v: Dict[str, Union[int, bool]]) -> None:
        """Print statistics for a specific index.

        Args:
            model: The model name (index label with dots instead of hyphens).
            v: Dictionary containing index statistics.
        """
        print(f"{model}")
        print(f"  Documents: {v['numberOfDocuments']}")
        if v["isIndexing"] is True:
            print("  INDEXING")
        print("")
