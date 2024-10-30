import contextlib
import sys

from requests.exceptions import HTTPError
import arrow
from django.utils.functional import cached_property
from meilisearch.index import Index

from .utils import get_document_fields, get_index_label, weak_lru

try:
    from cacheops import invalidate_model

    USING_CACHEOPS = True
except ImportError:
    USING_CACHEOPS = False


class MeiliIndexError(Exception):
    pass


class MeiliSearchModelIndex:
    """Creates a working index for each model sent to it."""

    def __init__(self, backend, model):
        """
        Initialize the MeiliSearchModelIndex.

        Args:
            backend (MeiliSearchBackend): The backend instance.
            model (Model): The Django model to be indexed.
        """
        self.backend = backend
        self.client = backend.client
        self.model = model
        self.model_fields = set(_.name for _ in model._meta.fields)
        self.name = model._meta.label
        self.index = self._set_index(model)
        self.update_strategy = backend.update_strategy
        self.update_delta = backend.update_delta
        self.delta_fields = [
            "created_at",
            "updated_at",
            "first_published_at",
            "last_published_at",
        ]

    def _update_stop_words(self, label):
        """
        Update the stop words for the given index.

        Args:
            label (str): The label of the index to update.
        """
        try:
            self.client.index(label).update_settings(
                {
                    "stopWords": self.backend.stop_words,
                },
            )
        except Exception:
            sys.stdout.write(f"WARN: Failed to update stop words on {label}\n")

    # @weak_lru()
    def _get_index_settings(self, label):
        """
        Get the settings for the index.

        Args:
            label (str): The label of the index.

        Raises:
            MeiliIndexError: If unable to get the index settings.
        """
        try:
            self.client.get_index(label).get_settings()
        except Exception as err:
            msg = f"Failed to get settings for {label}: {err}"
            raise MeiliIndexError(msg) from err

    def _set_index(self, model):
        """
        Set up the index for the given model.

        Args:
            model (Model): The Django model to create an index for.

        Returns:
            Index: The MeiliSearch index object.
        """
        if hasattr(self, 'index') and self.index:
            return self.index

        label = self._get_label(model)
        # if index doesn't exist, create
        try:
            index = self.client.index(label)
        except HTTPError:
            task = Index.create(self.client.http.config, label, {'primaryKey': 'id'})
            index = self.client.index(label)

        self.index = index

        return index

    def _get_label(self, model):
        if hasattr(self, 'label') and self.label:
            return self.label

        self.label = label = model._meta.label.replace('.', '-')
        return label

    def _rebuild(self):
        """Rebuild the index by deleting and recreating it."""
        self.index.delete()
        self._set_index(self.model)

    def add_model(self, model):
        """
        Add a model to the index. This method is a no-op as adding is done on initialization.

        Args:
            model (Model): The Django model to add to the index.
        """
        pass

    def get_index_for_model(self, model):
        """
        Get the index for the given model.

        Args:
            model (Model): The Django model to get the index for.

        Returns:
            MeiliSearchModelIndex: The index for the given model.
        """
        self._set_index(model)
        return self

    def _get_document_fields(self, model, item):
        """
        Get the fields for a document to be indexed.

        Args:
            model (Model): The Django model of the item.
            item: The item to be indexed.

        Returns:
            dict: The fields of the document to be indexed.
        """
        return get_document_fields(model, item)

    def _create_document(self, model, item):
        """
        Create a document to be indexed.

        Args:
            model (Model): The Django model of the item.
            item: The item to be indexed.

        Returns:
            dict: The document to be indexed.
        """
        doc_fields = dict(self._get_document_fields(model, item))
        doc_fields.update(id=item.id)
        return doc_fields

    def refresh(self):
        """Refresh the index. This method is a no-op in the current implementation."""
        pass

    def add_item(self, item):
        """
        Add a single item to the index.

        Args:
            item: The item to be added to the index.
        """
        if self.update_strategy == "delta":
            checked = self._check_deltas([item])
            if len(checked):
                item = checked[0]

        doc = self._create_document(self.model, item)
        if self.update_strategy == "soft":
            self.index.update_documents([doc])
        else:
            self.index.add_documents([doc])

    def add_items(self, item_model, items):
        """
        Add multiple items to the index.

        Args:
            item_model (Model): The Django model of the items.
            items (list): The items to be added to the index.

        Returns:
            bool: True if the operation was successful.
        """
        if USING_CACHEOPS:
            with contextlib.suppress(Exception):
                invalidate_model(item_model)

        chunks = [items[x : x + 100] for x in range(0, len(items), 100)]

        for chunk in chunks:
            if self.update_strategy == "delta":
                chunk = self._check_deltas(chunk)
            prepared = [self._create_document(self.model, item) for item in chunk]
            with contextlib.suppress(Exception):
                if prepared:
                    if self.update_strategy in ["soft", "delta"]:
                        self.index.update_documents(prepared)
                    else:
                        self.index.add_documents(prepared)
        return True

    @cached_property
    def _has_date_fields(self):
        """
        Check if the model has any of the delta fields.

        Returns:
            bool: True if the model has any of the delta fields, False otherwise.
        """
        return bool(self.model_fields.intersection(self.delta_fields))

    def _check_deltas(self, objects):
        """
        Filter objects based on the delta update strategy.

        Args:
            objects (list): The objects to be filtered.

        Returns:
            list: The filtered list of objects.
        """
        filtered = []
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

    def delete_item(self, obj):
        """
        Delete an item from the index.

        Args:
            obj: The object to be deleted from the index.
        """
        self.index.delete_document(obj.id)

    def delete_all_documents(self):
        """
        Delete all documents from the index.
        """
        self.index.delete_all_documents()

    def search(self, query):
        """
        Perform a search on the index.

        Args:
            query (str): The search query.

        Returns:
            dict: The search results.
        """
        return self.index.search(query, self.backend.search_params)

    def __str__(self):
        """
        Get a string representation of the index.

        Returns:
            str: The name of the index.
        """
        return self.name


class DummyModelIndex:
    """This class enables the SKIP_MODELS feature by providing a
    dummy model index that we can add things to without it actually
    doing anything.
    """

    def add_model(self, model):
        pass

    def add_items(self, model, chunk):
        pass
