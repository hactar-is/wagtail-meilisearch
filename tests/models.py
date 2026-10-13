from django.db import models
from wagtail.search import index


class Author(index.Indexed, models.Model):
    name = models.CharField(max_length=255)

    search_fields = [index.SearchField("name")]

    class Meta:
        app_label = "tests"


class Book(index.Indexed, models.Model):
    title = models.CharField(max_length=255)
    author = models.ForeignKey(Author, null=True, on_delete=models.SET_NULL)

    search_fields = [
        index.SearchField("title", boost=10),
        index.AutocompleteField("title"),
        index.RelatedFields("author", [index.SearchField("name", boost=5)]),
        index.FilterField("author"),
    ]

    class Meta:
        app_label = "tests"
