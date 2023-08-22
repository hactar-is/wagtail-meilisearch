# stdlib
import sys
import time
from typing import Optional

# 3rd party
import arrow
from django.db.models import Model, Manager, QuerySet
from wagtail.search.index import FilterField, SearchField, RelatedFields, AutocompleteField


try:
    from cacheops import invalidate_model
    USING_CACHEOPS = True
except ImportError:
    USING_CACHEOPS = False

try:
    from django.utils.encoding import force_text
except ImportError:
    from django.utils.encoding import force_str
    force_text = force_str


AUTOCOMPLETE_SUFFIX = '_ngrams'
FILTER_SUFFIX = '_filter'


def _get_field_mapping(field):
    if isinstance(field, FilterField):
        return field.field_name + FILTER_SUFFIX
    if isinstance(field, AutocompleteField):
        return field.field_name + AUTOCOMPLETE_SUFFIX
    return field.field_name


def timeit(method):
    """Decorator for timing the performance of a function.
    """
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()
        print('%2.2f sec %r (%r, %r)\n' % (te - ts, method.__name__, args, kw))
        return result

    return timed


class MeiliSearchModelIndex:

    """Creats a working index for each model sent to it.
    """

    def __init__(self, backend, model):
        """Initialise an index for `model`

        Args:
            backend (MeiliSearchBackend): A backend instance
            model (django.db.Model): Should be able to pass any model here but it's most
                likely to be a subclass of wagtail.core.models.Page
        """
        self.backend = backend
        self.client = backend.client
        self.query_limit = backend.query_limit
        self.model = model
        self.name = model._meta.label
        self.index = self._set_index(model)
        self.search_params = {
            'limit': self.query_limit,
            'attributesToRetrieve': ['id', 'first_published_at'],
            'showMatchesPosition': True,
        }
        self.update_strategy = backend.update_strategy
        self.update_delta = backend.update_delta
        self.delta_fields = [
            'created_at', 'updated_at', 'first_published_at', 'last_published_at',
        ]

    # @timeit
    def _update_stop_words(self, label):
        try:
            self.client.index(label).update_settings(
                {
                    'stopWords': self.backend.stop_words,
                },
            )
        except Exception:
            sys.stdout.write(f'WARN: Failed to update stop words on {label}\n')

    # @timeit
    def _update_ranking_rules(self, label):
        try:
            self.client.index(label).update_settings(
                {
                    'rankingRules': self.backend.ranking_rules,
                },
            )
        except Exception:
            sys.stdout.write(f'WARN: Failed to update ranking_rules on {label}\n')

    # @timeit
    def _set_index(self, model):
        if hasattr(self, 'index') and self.index:
            return self.index

        label = self._get_label(model)
        # if index doesn't exist, create
        try:
            self.client.get_index(label).get_settings()
        except Exception:
            index = self.client.create_index(uid=label, options={'primaryKey': 'id'})
            self._apply_settings(label)
        else:
            index = self.client.get_index(label)

        # Add filter / facet fields
        filter_fields = ['content_type_id_filter']
        for field in model.get_search_fields():
            if isinstance(field, FilterField):
                try:  # noqa: SIM105
                    filter_fields.append(_get_field_mapping(field))
                    # yield _get_field_mapping(field), self.prepare_value(field.get_value(item))
                except Exception:  # noqa: S110
                    pass

        index.update_filterable_attributes(filter_fields)

        self.index = index

        return index

    # @timeit
    def _apply_settings(self, label):
        self._update_stop_words(label)
        self._update_ranking_rules(label)

    # @timeit
    def _get_label(self, model):
        if hasattr(self, 'label') and self.label:
            return self.label

        self.label = label = model._meta.label.replace('.', '-')
        return label

    # @timeit
    def _rebuild(self):
        self.index.delete()
        self._set_index(self.model)

    # @timeit
    def add_model(self, model):
        # Adding done on initialisation
        pass

    # @timeit
    def get_index_for_model(self, model):
        self._set_index(model)
        return self

    # @timeit
    def prepare_value(self, value):
        """Makes sure `value` is something we can save in the index.

        Args:
            value (UNKNOWN): This could be anything.

        Returns:
            str: A String representation of whatever `value` was
        """
        if not value:
            return ''
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return ', '.join(self.prepare_value(item) for item in value)
        if isinstance(value, dict):
            return ', '.join(self.prepare_value(item)
                             for item in value.values())
        if callable(value):
            return force_text(value())
        return force_text(value)

    # @timeit
    def _get_document_fields(self, model, item):
        """Borrowed from Wagtail-Whoosh
        Walks through the model's search fields and returns stuff the way the index is
        going to want it.

        Args:
            model (db.Model): The model class we want the fields for
            item (db.Model): The model instance we want the fields for

        Yields:
            TYPE: Description
        """
        for field in model.get_search_fields():
            if isinstance(field, (SearchField, FilterField, AutocompleteField)):
                try:  # noqa: SIM105
                    yield _get_field_mapping(field), self.prepare_value(field.get_value(item))
                except Exception:  # noqa: S110
                    pass
            if isinstance(field, RelatedFields):
                value = field.get_value(item)
                if isinstance(value, (Manager, QuerySet)):
                    qs = value.all()
                    for sub_field in field.fields:
                        sub_values = qs.values_list(sub_field.field_name, flat=True)
                        try:  # noqa: SIM105
                            yield '{0}__{1}'.format(
                                field.field_name, _get_field_mapping(sub_field)), \
                                self.prepare_value(list(sub_values))
                        except Exception:  # noqa: S110
                            pass
                if isinstance(value, Model):
                    for sub_field in field.fields:
                        try:  # noqa: SIM105
                            yield '{0}__{1}'.format(
                                field.field_name, _get_field_mapping(sub_field)),\
                                self.prepare_value(sub_field.get_value(value))
                        except Exception:  # noqa: S110, PERF203
                            pass

    # @timeit
    def _create_document(self, model, item):
        """Create a dict containing the fields we want to send to MeiliSearch

        Args:
            model (db.Model): The model class we're indexing
            item (db.Model): The model instance we're indexing

        Returns:
            dict: A dict representation of the model
        """
        doc_fields = dict(self._get_document_fields(model, item))
        doc_fields.update(id=item.id)
        document = {}
        document.update(doc_fields)
        return document

    # @timeit
    def refresh(self):
        # TODO: Work out what this method is supposed to do because nothing is documented properly
        # It might want something to do with `client.get_indexes()`, but who knows, there's no
        # docstrings anywhere in the reference classes.
        pass

    # @timeit
    def add_item(self, item):
        if self.update_strategy == 'delta':
            # We send it a list and get back a list, though that list might be empty
            checked = self._check_deltas([item])
            if len(checked):
                item = checked[0]

        doc = self._create_document(self.model, item)
        if self.update_strategy == 'soft':
            self.index.update_documents([doc])
        else:
            self.index.add_documents([doc])

    # @timeit
    def add_items(self, item_model, items):
        """Adds items in bulk to the index. If we're adding stuff through the `update_index`
        management command, we'll receive these in chunks of 1000.

        We're then splitting those chunks into smaller chunks of 100, I think that helps
        not overload stuff, but it would be good TODO tests to verify this.

        Args:
            item_model (db.Model): The model class we're indexing
            items (list): A list containing a bunch of items to index.

        Returns:
            bool: True
        """
        prepared = []

        # Ensure we're not indexing something stale from the cache
        # This also stops redis from overloading during the indexing
        if USING_CACHEOPS is True:
            try:  # noqa: SIM105
                invalidate_model(item_model)
            except Exception:  # noqa: S110
                pass

        # split items into chunks of 100
        chunks = [items[x:x + 100] for x in range(0, len(items), 100)]

        for chunk in chunks:
            if self.update_strategy == 'delta':
                chunk = self._check_deltas(chunk)
            prepared = []
            for item in chunk:
                doc = self._create_document(self.model, item)
                prepared.append(doc)

            if len(prepared):
                if self.update_strategy == 'soft' or self.update_strategy == 'delta':
                    self.index.update_documents(prepared)
                else:
                    self.index.add_documents(prepared)
            del(chunk)

        return True

    # @timeit
    def _has_date_fields(self, obj):
        find = self.delta_fields
        fields = [_.name for _ in obj._meta.fields]
        rv = any(item in find for item in fields)
        return rv

    # @timeit
    def _check_deltas(self, objects: list) -> list:
        """Takes a list of objects and removes any where the last_published_at, first_published_at,
        created_at or updated_at are outside of the time delta.

        TODO: This looks ugly, and is probably slow.

        Args:
            objects (list): A list of model instances
        """
        filtered = []
        since = arrow.now().shift(**self.update_delta).datetime
        for obj in objects:
            if self._has_date_fields(obj):
                for field in self.delta_fields:
                    if hasattr(obj, field):
                        val = getattr(obj, field)
                        try:
                            if val and val > since:
                                filtered.append(obj)
                                continue
                        except TypeError:
                            pass

        return filtered

    # @timeit
    def delete_item(self, obj):
        self.index.delete_document(obj.id)

    # @timeit
    def search(self, query, extras: Optional[dict] = None):
        """Perform a search against a model index

        Args:
            query (str): The search term
            extras (dict): key value pairs of extra data to send to the meilisearch backend

        """
        if extras is None:
            extras = {}
        params = self.search_params
        if len(extras):
            params.update(**extras)

        return self.index.search(query, params)

    def __repr__(self):
        return f"MeiliSearchModelIndex <{self.name}>"

    def __str__(self):
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
