import sys

# stdlib
from operator import itemgetter
from functools import lru_cache

# 3rd party
import arrow
import meilisearch
from django.apps import apps
from django.db.models import Q, Case, When, Model, Manager, QuerySet
from wagtail.search.index import (
    FilterField, SearchField, RelatedFields, AutocompleteField, class_is_indexed,
    get_indexed_models,
)
from wagtail.search.utils import OR
from wagtail.search.backends.base import (
    BaseSearchBackend, BaseSearchResults, EmptySearchResults, BaseSearchQueryCompiler,
)
from wagtail.search.query import PlainText, Phrase, Fuzzy

try:
    from django.utils.encoding import force_text
except ImportError:
    from django.utils.encoding import force_str
    force_text = force_str


from .settings import STOP_WORDS
import contextlib

try:
    from cacheops import invalidate_model
    USING_CACHEOPS = True
except ImportError:
    USING_CACHEOPS = False


AUTOCOMPLETE_SUFFIX = '_ngrams'
FILTER_SUFFIX = '_filter'


def _get_field_mapping(field):
    if isinstance(field, FilterField):
        return field.field_name + FILTER_SUFFIX
    if isinstance(field, AutocompleteField):
        return field.field_name + AUTOCOMPLETE_SUFFIX
    return field.field_name


def get_index_label(model):
    return model._meta.label.replace('.', '-')


@lru_cache()
def _cacheable_create_document(doc_fields, item):
    """Create a dict containing the fields we want to send to MeiliSearch.

    This lives outside of the class due to the use of @lru_cache, see:
    https://docs.astral.sh/ruff/rules/cached-instance-method/

    Args:
        doc_fields (dict): Description
        item (db.Model): The model instance we're indexing

        Returns:
            dict: A dict representation of the model
    """
    doc_fields.update(id=item.id)
    document = {}
    document.update(doc_fields)
    return document


class MeiliSearchModelIndex:

    """Creats a working index for each model sent to it.
    """

    def __init__(self, backend, model):
        """Initialise an index for `model`

        Args:
            backend (MeiliSearchBackend): A backend instance
            model (django.db.Model): Should be able to pass any model here but it's most
                likely to be a subclass of wagtail.models.Page
        """
        self.backend = backend
        self.client = backend.client
        self.model = model
        self.name = model._meta.label
        self.index = self._set_index(model)
        self.update_strategy = backend.update_strategy
        self.update_delta = backend.update_delta
        self.delta_fields = [
            'created_at', 'updated_at', 'first_published_at', 'last_published_at',
        ]

    def _update_stop_words(self, label):
        try:
            self.client.index(label).update_settings(
                {
                    'stopWords': self.backend.stop_words,
                },
            )
        except Exception:
            sys.stdout.write(f'WARN: Failed to update stop words on {label}\n')

    def _set_index(self, model):
        label = get_index_label(model)
        # if index doesn't exist, create
        try:
            self.client.get_index(label).get_settings()
        except Exception:
            index = self.client.create_index(uid=label, options={'primaryKey': 'id'})
            self._update_stop_words(label)
        else:
            index = self.client.get_index(label)

        return index

    def _rebuild(self):
        self.index.delete()
        self._set_index(self.model)

    def add_model(self, model):
        # Adding done on initialisation
        pass

    def get_index_for_model(self, model):
        self._set_index(model)
        return self

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

    def _get_document_fields(self, model, item):
        """Borrowed from Wagtail-Whoosh
        Walks through the model's search fields and returns stuff the way the index is
        going to want it.

        Todo:
            * Make sure all of this is usable by MeiliSearch

        Args:
            model (db.Model): The model class we want the fields for
            item (db.Model): The model instance we want the fields for

        Yields:
            TYPE: Description
        """
        for field in model.get_search_fields():
            if isinstance(field, (SearchField, FilterField, AutocompleteField)):
                with contextlib.suppress(Exception):
                    yield _get_field_mapping(field), self.prepare_value(field.get_value(item))
            if isinstance(field, RelatedFields):
                value = field.get_value(item)
                if isinstance(value, (Manager, QuerySet)):
                    qs = value.all()
                    for sub_field in field.fields:
                        sub_values = qs.values_list(sub_field.field_name, flat=True)
                        with contextlib.suppress(Exception):
                            yield '{0}__{1}'.format(
                                field.field_name, _get_field_mapping(sub_field)), \
                                self.prepare_value(list(sub_values))
                if isinstance(value, Model):
                    for sub_field in field.fields:
                        with contextlib.suppress(Exception):
                            yield '{0}__{1}'.format(
                                field.field_name, _get_field_mapping(sub_field)),\
                                self.prepare_value(sub_field.get_value(value))

    def _create_document(self, model, item):
        """Create a dict containing the fields we want to send to MeiliSearch

        Args:
            model (db.Model): The model class we're indexing
            item (db.Model): The model instance we're indexing

        Returns:
            dict: A dict representation of the model
        """
        doc_fields = dict(self._get_document_fields(model, item))
        document = _cacheable_create_document(doc_fields, item)
        return document

    def refresh(self):
        # TODO: Work out what this method is supposed to do because nothing is documented properly
        # It might want something to do with `client.get_indexes()`, but who knows, there's no
        # docstrings anywhere in the reference classes.
        pass

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
            with contextlib.suppress(Exception):
                invalidate_model(item_model)

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
            del (chunk)

        return True

    def _has_date_fields(self, obj):
        find = self.delta_fields
        fields = [_.name for _ in obj._meta.fields]
        rv = any(item in find for item in fields)
        return rv

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

    def delete_item(self, obj):
        self.index.delete_document(obj.id)

    def search(self, query):
        return self.index.search(query, self.backend.search_params)

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


class MeiliSearchRebuilder:
    def __init__(self, model_index):
        self.index = model_index
        self.uid = get_index_label(self.index.model)
        self.dummy_index = DummyModelIndex()

    def start(self):
        """This is the thing that starts of a rebuild of the search
        index. We offer three strategies, `hard`, `soft` and `delta`.

        * `hard` will delete every document in the index and try to add them anew
        * `soft` will do an "add or update" for each document
        * `delta` will attempt to only update documents that have been saved in the
            last X amount of time

        The trade off here is that a `hard` update is CPU intensive for quite a long time, while
        a `soft` update can leave fields in existing indexed documents that aren't in the new
        document. Once a large site is fully indexed, it should be pretty safe to switch to a
        `delta` strategy which would be the least CPU intensive of all.
        """
        if self.index.model._meta.label in self.index.backend.skip_models:
            sys.stdout.write(f'SKIPPING: {self.index.model._meta.label}\n')
            return self.dummy_index

        strategy = self.index.backend.update_strategy
        if strategy == 'soft' or strategy == 'delta':
            # SOFT UPDATE STRATEGY
            index = self.index.backend.client.get_index(self.uid)
        else:
            # HARD UPDATE STRATEGY
            old_index = self.index.backend.client.get_index(self.uid)
            old_index.delete_all_documents()

        model = self.index.model
        index = self.index.backend.get_index_for_model(model)
        return index

    def finish(self):
        pass


class MeiliSearchQueryCompiler(BaseSearchQueryCompiler):

    def _process_lookup(self, field, lookup, value):
        # Also borrowed from wagtail-whoosh
        return Q(**{field.get_attname(self.queryset.model) + '__' + lookup: value})

    def _connect_filters(self, filters, connector, negated):
        # Also borrowed from wagtail-whoosh
        if connector == 'AND':
            q = Q(*filters)
        elif connector == 'OR':
            q = OR([Q(fil) for fil in filters])
        else:
            return None

        if negated:
            q = ~q

        return q


class MeiliSearchAutocompleteQueryCompiler(MeiliSearchQueryCompiler):
    def _get_fields_names(self):
        model = self.queryset.model
        for field in model.get_autocomplete_search_fields():
            yield _get_field_mapping(field)


@lru_cache()
def get_descendant_models(model):
    """
    Borrowed from Wagtail-Whoosh
    Returns all descendants of a model
    e.g. for a search on Page, return [HomePage, ContentPage, Page] etc.
    """
    descendant_models = [
        other_model for other_model in apps.get_models() if issubclass(other_model, model)
    ]
    return descendant_models


class MeiliSearchResults(BaseSearchResults):
    supports_facet = False

    def _get_field_boosts(self, model):
        boosts = {}
        for field in model.search_fields:
            if isinstance(field, SearchField) and hasattr(field, 'boost'):
                boosts[field.field_name] = field.boost

        return boosts

    @property
    def models(self):
        return get_descendant_models(self.query_compiler.queryset.model)

    @property
    def query_string(self):
        query = self.query_compiler.query
        if isinstance(query, (PlainText, Phrase, Fuzzy)):
            return query.query_string
        return ''

    def _do_search(self):
        models = self.models
        terms = self.query_string

        models_boosts = {}
        for model in models:
            label = get_index_label(model)
            models_boosts[label] = self._get_field_boosts(model)

        results = [
            {
                **item,
                'boosts': models_boosts[items['indexUid']],
            }
            for items in self.backend.client.multi_search([
                {
                    'indexUid': index_uid,
                    'q': terms,
                    **self.backend.search_params,
                }
                for index_uid in models_boosts
            ])['results']
            for item in items['hits']
        ]

        """At this point we have a list of results that each look something like this
        (with various fields snipped)...

        {
            'id': 45014,
            'boosts': {
                'title': 10
            },
            '_matchesPosition': {
                'title_filter': [
                    {'start': 0, 'length': 6}
                ],
                'title': [
                    {'start': 0, 'length': 6}
                ],
                'excerpt': [
                    {'start': 20, 'length': 6}
                ],
                'title_ngrams': [
                    {'start': 0, 'length': 6}
                ],
                'body': [
                    {'start': 66, 'length': 6},
                    {'start': 846, 'length': 6},
                    {'start': 1888, 'length': 6},
                    {'start': 2250, 'length': 6},
                    {'start': 2262, 'length': 6},
                    {'start': 2678, 'length': 6},
                    {'start': 3307, 'length': 6}
                ]
            }
        }
        """
        # Let's annotate this list working out some kind of basic score for each item
        # The simplest way is probably to len(str(item['_matchesPosition'])) which for the
        # above example returns a score of 386 and for the bottom result in my test set is
        # just 40.
        for item in results:
            score = 0
            for key in item['_matchesPosition']:
                try:
                    boost = item['boosts'].get(key, 1)
                except Exception:
                    boost = 1

                if not boost:
                    boost = 1

                score += len(str(item['_matchesPosition'][key])) * boost

            item['score'] = score

        sorted_results = sorted(results, key=itemgetter('score'), reverse=True)
        sorted_ids = [_['id'] for _ in sorted_results]

        qc = self.query_compiler
        window_sorted_ids = sorted_ids[self.start:self.stop]
        results = qc.queryset.filter(pk__in=window_sorted_ids)

        # This piece of utter genius is borrowed wholesale from wagtail-whoosh after I spent
        # several hours trying and failing to work out how to do this.
        if qc.order_by_relevance:
            # Retrieve the results from the db, but preserve the order by score
            preserved_order = Case(
                *[When(pk=pk, then=pos) for pos, pk in enumerate(window_sorted_ids)],
            )
            results = results.order_by(preserved_order)

        return results.distinct()

    def _do_count(self):
        models = self.models
        terms = self.query_string
        indexes_uids = [
            get_index_label(model)
            for model in models
        ]
        return sum([
            results['totalHits']
            for results in self.backend.client.multi_search([
                {
                    'indexUid': index_uid,
                    'q': terms,
                    'attributesToRetrieve': [],
                    'hitsPerPage': 0,
                }
                for index_uid in indexes_uids
            ])['results']
        ])


class MeiliSearchBackend(BaseSearchBackend):

    query_compiler_class = MeiliSearchQueryCompiler
    autocomplete_query_compiler_class = MeiliSearchAutocompleteQueryCompiler
    rebuilder_class = MeiliSearchRebuilder
    results_class = MeiliSearchResults

    def __init__(self, params):
        super().__init__(params)
        self.params = params
        try:
            self.client = meilisearch.Client(
                '{}:{}'.format(self.params['HOST'], self.params['PORT']),
                self.params['MASTER_KEY'],
            )
        except Exception:
            raise
        self.stop_words = params.get('STOP_WORDS', STOP_WORDS)
        self.skip_models = params.get('SKIP_MODELS', [])
        self.update_strategy = params.get('UPDATE_STRATEGY', 'soft')
        self.query_limit = params.get('QUERY_LIMIT', 999999)
        self.search_params = {
            'limit': self.query_limit,
            'attributesToRetrieve': ['id'],
            'showMatchesPosition': True,
        }
        self.update_delta = None
        if self.update_strategy == 'delta':
            self.update_delta = params.get('UPDATE_DELTA', {'weeks': -1})

    def _refresh(self, uid, model):
        index = self.client.get_index(uid)
        index.delete()
        new_index = self.get_index_for_model(model)
        return new_index

    def get_index_for_model(self, model):
        return MeiliSearchModelIndex(self, model)

    def get_rebuilder(self):
        return None

    def reset_index(self):
        raise NotImplementedError

    def add_type(self, model):
        self.get_index_for_model(model).add_model(model)

    def refresh_index(self):
        refreshed_indexes = []
        for model in get_indexed_models():
            index = self.get_index_for_model(model)
            if index not in refreshed_indexes:
                index.refresh()
                refreshed_indexes.append(index)

    def add(self, obj):
        self.get_index_for_model(type(obj)).add_item(obj)

    def add_bulk(self, model, obj_list):
        self.get_index_for_model(model).add_items(model, obj_list)

    def delete(self, obj):
        self.get_index_for_model(type(obj)).delete_item(obj)

    def _search(self, query_compiler_class, query, model_or_queryset, partial_match, **kwargs):  # noqa: ARG002
        # Find model/queryset
        if isinstance(model_or_queryset, QuerySet):
            model = model_or_queryset.model
            queryset = model_or_queryset
        else:
            model = model_or_queryset
            queryset = model_or_queryset.objects.all()

        # Model must be a class that is in the index
        if not class_is_indexed(model):
            return EmptySearchResults()

        # Check that theres still a query string after the clean up
        if query == "":
            return EmptySearchResults()

        # Search
        search_query = query_compiler_class(
            queryset, query, **kwargs,
        )

        # Check the query
        search_query.check()

        return self.results_class(self, search_query)

    def search(
            self, query, model_or_queryset, fields=None, operator=None,
            order_by_relevance=True, partial_match=True):
        return self._search(
            self.query_compiler_class,
            query,
            model_or_queryset,
            fields=fields,
            operator=operator,
            order_by_relevance=order_by_relevance,
            partial_match=partial_match,
        )

    def autocomplete(
            self, query, model_or_queryset, fields=None, operator=None, order_by_relevance=True):
        if self.autocomplete_query_compiler_class is None:
            msg = "This search backend does not support the autocomplete API"
            raise NotImplementedError(msg)

        return self._search(
            self.autocomplete_query_compiler_class,
            query,
            model_or_queryset,
            fields=fields,
            operator=operator,
            order_by_relevance=order_by_relevance,
        )


SearchBackend = MeiliSearchBackend
