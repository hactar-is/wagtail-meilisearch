from tests.models import Book
from wagtail_meilisearch.utils import get_document_fields


def test_document_fields_use_current_values():
    book = Book(pk=1, title="Old title")
    assert get_document_fields(Book, book)["title"] == "Old title"

    book.title = "New title"

    assert get_document_fields(Book, book)["title"] == "New title"


def test_document_fields_for_another_instance_with_same_pk():
    get_document_fields(Book, Book(pk=2, title="First"))

    assert get_document_fields(Book, Book(pk=2, title="Second"))["title"] == "Second"
