import contextlib

# Import for type checking only
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Type, cast

import arrow
from django.core.cache import cache
from django.db.models import Model
from django.utils.functional import cached_property
from meilisearch.index import Index
from requests.exceptions import HTTPError

from .utils import get_document_fields

if TYPE_CHECKING:
    from .backend import MeiliSearchBackend
    from .settings import MeiliSettings

try:
    from cacheops import invalidate_model

    USING_CACHEOPS = True
except ImportError:
    USING_CACHEOPS = False


class MeiliIndexError(Exception):
    pass


class MeiliIndexRegistry:
    """A registry of all the indexes we're using.

    This class maintains a registry of all MeiliSearch indexes and provides methods
    to retrieve and manage them.

    Attributes:
        indexes (Dict[str, MeiliSearchModelIndex]): Dictionary mapping labels to index objects.
    """

    indexes: Dict[str, "MeiliSearchModelIndex"] = {}

    def __init__(self, backend: Any, settings: Any) -> None:
        """Initialize the MeiliIndexRegistry.

        Args:
            backend: The search backend instance.
            settings: The settings for the search backend.
        """
        self.backend = backend
        self.client = backend.client
        self.settings = settings

    def _get_label(self, model: Type[Model]) -> str:
        """Get a unique label for the model's index.

        Args:
            model: The model to get the label for.

        Returns:
            str: A unique label for the model's index.
        """
        label = model._meta.label.replace(".", "-")
        return label

    def get_index_for_model(self, model: Type[Model]) -> "MeiliSearchModelIndex":
        """Get the index for a specific model.

        This gets called by the get_index_for_model in the backend which in turn is called by
        update_index management command so needs to exist as a method on the backend.

        Args:
            model: The model we're looking for the index for.

        Returns:
            MeiliSearchModelIndex: The index for the model.
        """
        label = self._get_label(model)

        # See if it's in our registry
        if label in self.indexes:
            return self.indexes.get(label)

        # See if it's in the cache
        cache_key = f"meili_index_{label}"
        index = cache.get(cache_key)
        if index is None:
            index = MeiliSearchModelIndex(
                backend=self.backend,
                model=model,
            )
            cache.set(cache_key, index)

        self.register(label, index)
        return index

    def register(self, label: str, index: "MeiliSearchModelIndex") -> None:
        """Register an index with a label.

        Args:
            label: The label to register the index under.
            index: The index to register.
        """
        self.indexes[label] = index

    def _refresh(self, uid: str, model: Type[Model]) -> "MeiliSearchModelIndex":
        """Refresh an index by deleting and recreating it.

        Args:
            uid: The unique ID of the index to refresh.
            model: The model associated with the index.

        Returns:
            MeiliSearchModelIndex: The newly created index.
        """
        index = self.client.get_index(uid)
        index.delete()
        new_index = self.get_index_for_model(model)
        return new_index


class MeiliSearchModelIndex:
    """Creates a working index for each model sent to it."""

    def __init__(self, backend: Any, model: Optional[Type[Model]]) -> None:
        """Initialize the MeiliSearchModelIndex.

        Creates a working index for the specified model and sets up all the necessary
        properties for interacting with MeiliSearch.

        Args:
            backend: The backend instance.
            model: The Django model to be indexed.
        """
        self.backend: "MeiliSearchBackend" = backend
        self.settings: "MeiliSettings" = backend.settings
        settings: "MeiliSettings" = self.settings
        self.model: Optional[Type[Model]] = model

        self.client: Any = backend.client
        self.query_limit: int = settings.query_limit
        self.name: str = "" if model is None else model._meta.label
        self.model_fields: Set[str] = set()
        if model is not None:
            self.model_fields = set(_.name for _ in model._meta.fields)

        self.index: Index = self._set_index(model)
        self.search_params: Dict[str, Any] = {
            "limit": self.query_limit,
            "attributesToRetrieve": ["id", "first_published_at"],
            "showMatchesPosition": True,
        }
        self.update_strategy: str = settings.update_strategy
        self.update_delta: Optional[Dict[str, int]] = settings.update_delta
        self.delta_fields: List[str] = [
            "created_at",
            "updated_at",
            "first_published_at",
            "last_published_at",
        ]
        self.label: str = "" if model is None else self._get_label(model)

    def _get_index_settings(self, label: str) -> Dict[str, Any]:
        """Get the settings for the index.

        Retrieves the current settings for the specified MeiliSearch index.

        Args:
            label: The label of the index.

        Returns:
            Dict[str, Any]: The settings for the index.

        Raises:
            MeiliIndexError: If unable to get the index settings.
        """
        try:
            return self.client.get_index(label).get_settings()
        except Exception as err:
            msg = f"Failed to get settings for {label}: {err}"
            raise MeiliIndexError(msg) from err

    def _set_index(self, model: Optional[Type[Model]]) -> Index:
        """Set up the index for the given model.

        Creates or retrieves the MeiliSearch index for the specified model.

        Args:
            model: The Django model to create an index for.

        Returns:
            Index: The MeiliSearch index object.
        """
        if hasattr(self, "index") and self.index:
            return self.index

        if model is None:
            return cast("Index", None)  # This should never be reached in practice

        label = self._get_label(model)
        # if index doesn't exist, create
        try:
            index = self.client.index(label)
        except HTTPError:
            # Create the index with primary key setting
            Index.create(self.client.http.config, label, {"primaryKey": "id"})
            index = self.client.index(label)

        self.index = index

        return index

    def _get_label(self, model: Type[Model]) -> str:
        """Get a unique label for the model's index.

        Args:
            model: The model to get the label for.

        Returns:
            str: A unique label for the model's index.
        """
        if hasattr(self, "label") and self.label:
            return self.label

        self.label = label = model._meta.label.replace(".", "-")
        return label
    
    def get_key(self) -> str:
        """Get the unique key for this index
    
        Returns:
            str: This index's unique key
        """
        return self.label

    def _rebuild(self) -> None:
        """Rebuild the index by deleting and recreating it.

        This method completely recreates the index, which will remove all
        documents and reset all settings.
        """
        self.index.delete()
        self._set_index(self.model)

    def add_model(self, model: Type[Model]) -> None:
        """
        Add a model to the index. This method is a no-op as adding is done on initialization.

        Args:
            model (Model): The Django model to add to the index.
        """
        pass

    def get_index_for_model(self, model: Type[Model]) -> "MeiliSearchModelIndex":
        """
        Get the index for the given model.

        Args:
            model (Model): The Django model to get the index for.

        Returns:
            MeiliSearchModelIndex: The index for the given model.
        """
        self._set_index(model)
        return self

    def _get_document_fields(self, model: Type[Model], item: Model) -> Dict[str, Any]:
        """Get the fields for a document to be indexed.

        Extracts all indexable fields from the item using the model's search field definitions.

        Args:
            model: The Django model of the item.
            item: The item to be indexed.

        Returns:
            Dict[str, Any]: The fields of the document to be indexed.
        """
        return get_document_fields(model, item)

    def _create_document(self, model: Type[Model], item: Model) -> Dict[str, Any]:
        """Create a document to be indexed.

        Builds a complete document dictionary with all fields and the ID for indexing.

        Args:
            model: The Django model of the item.
            item: The item to be indexed.

        Returns:
            Dict[str, Any]: The document to be indexed.
        """
        doc_fields = dict(self._get_document_fields(model, item))
        doc_fields.update(id=item.id)
        return doc_fields

    def refresh(self) -> None:
        """Refresh the index.

        This method is a no-op in the current implementation.
        It exists to maintain compatibility with the Wagtail search API.
        """
        pass

    def add_item(self, item: Model) -> None:
        """Add a single item to the index.

        Indexes a single model instance according to the current update strategy.
        If using the delta update strategy, only adds the item if it was modified
        within the delta time period.

        Args:
            item: The item to be added to the index.
        """
        if self.update_strategy == "delta":
            checked = self._check_deltas([item])
            if len(checked):
                item = checked[0]

        if self.model is None:
            return

        doc = self._create_document(self.model, item)
        if self.update_strategy == "soft":
            self.index.update_documents([doc])
        else:
            self.index.add_documents([doc])

    def add_items(self, item_model: Type[Model], items: List[Model]) -> bool:
        """Add multiple items to the index.

        Indexes multiple model instances according to the current update strategy.
        Processes items in chunks of 100 to avoid overwhelming the MeiliSearch instance.
        If using the delta update strategy, only adds items that were modified
        within the delta time period.

        Args:
            item_model: The Django model of the items.
            items: The items to be added to the index.

        Returns:
            bool: True if the operation was successful.
        """
        if USING_CACHEOPS:
            with contextlib.suppress(Exception):
                invalidate_model(item_model)

        chunks: List[List[Model]] = [items[x : x + 100] for x in range(0, len(items), 100)]

        for chunk in chunks:
            if self.update_strategy == "delta":
                chunk = self._check_deltas(chunk)
            if self.model is None:
                continue
            prepared = [self._create_document(self.model, item) for item in chunk]
            with contextlib.suppress(Exception):
                if prepared:
                    if self.update_strategy in ["soft", "delta"]:
                        self.index.update_documents(prepared)
                    else:
                        self.index.add_documents(prepared)
        return True

    @cached_property
    def _has_date_fields(self) -> bool:
        """Check if the model has any of the delta fields.

        Determines if the model has any fields that can be used for delta updates
        (created_at, updated_at, first_published_at, last_published_at).

        Returns:
            bool: True if the model has any of the delta fields, False otherwise.
        """
        return bool(self.model_fields.intersection(self.delta_fields))

    def _check_deltas(self, objects: List[Model]) -> List[Model]:
        """Filter objects based on the delta update strategy.

        When using the delta update strategy, this method filters the objects list
        to only include items that have been created or modified within the
        specified time period.

        Args:
            objects: The objects to be filtered.

        Returns:
            List[Model]: The filtered list of objects.
        """
        filtered: List[Model] = []
        if not self.update_delta:
            return filtered

        since = arrow.now().shift(**self.update_delta).datetime
        for obj in objects:
            if self._has_date_fields:
                for field in self.delta_fields:
                    if hasattr(obj, field):
                        val = getattr(obj, field)
                        try:
                            if val and val > since:
                                filtered.append(obj)
                                break
                        except TypeError:
                            pass
        return filtered

    def delete_item(self, obj: Model) -> None:
        """Delete an item from the index.

        Removes a single document from the index based on its ID.

        Args:
            obj: The object to be deleted from the index.
        """
        self.index.delete_document(obj.id)

    def delete_all_documents(self) -> None:
        """Delete all documents from the index.

        Removes all documents from the index while preserving the index settings.
        This is faster than deleting and recreating the index.
        """
        self.index.delete_all_documents()

    def search(self, query: str, extras: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform a search on the index.

        Executes a search query against the MeiliSearch index with the specified
        search parameters.

        Args:
            query: The search query string.
            extras: Optional additional search parameters to include in the request.
                These will be merged with the default search parameters.

        Returns:
            Dict[str, Any]: The search results from MeiliSearch.
        """
        if extras is None:
            extras = {}
        params = self.backend.search_params
        if len(extras):
            params.update(**extras)

        return self.index.search(query, params)

    def __str__(self) -> str:
        """Get a string representation of the index.

        Returns the name of the index for easy identification.

        Returns:
            str: The name of the index.
        """
        return self.name


class DummyModelIndex:
    """A dummy model index that performs no actual indexing operations.

    This class enables the SKIP_MODELS feature by providing a dummy
    implementation of the MeiliSearchModelIndex interface that can receive
    add operations without actually indexing anything.

    This is useful for models that should be excluded from search but still
    need to go through the indexing workflow.
    """

    def add_model(self, model: Type[Model]) -> None:
        """Add a model to the index (no-op).

        Args:
            model: The model to be added (ignored).
        """
        pass

    def add_items(self, model: Type[Model], chunk: List[Model]) -> None:
        """Add items to the index (no-op).

        Args:
            model: The model of the items (ignored).
            chunk: The items to be added (ignored).
        """
        pass
