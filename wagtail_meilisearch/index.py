import contextlib
import sys

import arrow
from django.db import models
from wagtail.search.index import AutocompleteField, FilterField, RelatedFields, SearchField

from .utils import _get_field_mapping, get_index_label, prepare_value

try:
    from cacheops import invalidate_model

    USING_CACHEOPS = True
except ImportError:
    USING_CACHEOPS = False


class MeiliSearchModelIndex:
    """Creates a working index for each model sent to it."""

    def __init__(self, backend, model):
        self.backend = backend
        self.client = backend.client
        self.model = model
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
        try:
            self.client.index(label).update_settings(
                {
                    "stopWords": self.backend.stop_words,
                },
            )
        except Exception:
            sys.stdout.write(f"WARN: Failed to update stop words on {label}\n")

    def _set_index(self, model):
        label = get_index_label(model)
        try:
            self.client.get_index(label).get_settings()
        except Exception:
            index = self.client.create_index(uid=label, options={"primaryKey": "id"})
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

    def _get_document_fields(self, model, item):
        for field in model.get_search_fields():
            if isinstance(field, (SearchField, FilterField, AutocompleteField)):
                with contextlib.suppress(Exception):
                    yield _get_field_mapping(field), prepare_value(field.get_value(item))
            if isinstance(field, RelatedFields):
                value = field.get_value(item)
                if isinstance(value, (models.Manager, models.QuerySet)):
                    qs = value.all()
                    for sub_field in field.fields:
                        sub_values = qs.values_list(sub_field.field_name, flat=True)
                        with contextlib.suppress(Exception):
                            yield (
                                f"{field.field_name}__{_get_field_mapping(sub_field)}",
                                prepare_value(list(sub_values)),
                            )
                if isinstance(value, models.Model):
                    for sub_field in field.fields:
                        with contextlib.suppress(Exception):
                            yield (
                                f"{field.field_name}__{_get_field_mapping(sub_field)}",
                                prepare_value(sub_field.get_value(value)),
                            )

    def _create_document(self, model, item):
        doc_fields = dict(self._get_document_fields(model, item))
        doc_fields.update(id=item.id)
        return doc_fields

    def refresh(self):
        pass

    def add_item(self, item):
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
        if USING_CACHEOPS:
            with contextlib.suppress(Exception):
                invalidate_model(item_model)

        chunks = [items[x : x + 100] for x in range(0, len(items), 100)]

        for chunk in chunks:
            if self.update_strategy == "delta":
                chunk = self._check_deltas(chunk)
            prepared = [self._create_document(self.model, item) for item in chunk]

            if prepared:
                if self.update_strategy in ["soft", "delta"]:
                    self.index.update_documents(prepared)
                else:
                    self.index.add_documents(prepared)

        return True

    def _has_date_fields(self, obj):
        fields = [_.name for _ in obj._meta.fields]
        return any(field in self.delta_fields for field in fields)

    def _check_deltas(self, objects):
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
                                break
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
