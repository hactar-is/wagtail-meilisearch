from tests.models import Book
from wagtail_meilisearch.settings import MeiliSettings


def searchable_attributes(model):
    return MeiliSettings({})._ordered_fields(model)


def test_related_fields_are_searchable():
    assert "author__name" in searchable_attributes(Book)


def test_autocomplete_fields_use_their_document_key():
    attributes = searchable_attributes(Book)

    assert "title_ngrams" in attributes
    assert attributes.count("title") == 1


def test_filter_fields_are_not_searchable():
    assert not any(name.startswith("author_filter") for name in searchable_attributes(Book))


def test_attributes_ordered_by_boost():
    attributes = searchable_attributes(Book)

    assert attributes.index("title") < attributes.index("author__name")
    assert attributes.index("author__name") < attributes.index("title_ngrams")
