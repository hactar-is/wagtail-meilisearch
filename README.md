# Wagtail MeiliSearch

This is a (work in progress) Wagtail search backend for the [https://github.com/meilisearch/MeiliSearch](MeiliSearch) search engine.


## Installation

Once this is submitted to PyPI then it should just be...

`poetry add wagtail_meilisearch` or `pip install wagtail_meilisearch`

In the meantime, install it from git.

## Configuration

See the [https://docs.meilisearch.com/guides/advanced_guides/installation.html#environment-variables-and-flags](MeiliSearch docs) for info on the values you want to add here.

```
WAGTAILSEARCH_BACKENDS = {
    'default': {
        'BACKEND': 'wagtail_meilisearch.backend',
        'HOST': os.environ.get('MEILISEARCH_HOST', 'http://127.0.0.1'),
        'PORT': os.environ.get('MEILISEARCH_PORT', '7700'),
        'MASTER_KEY': os.environ.get('MEILI_MASTER_KEY', '')
    },
}
```

## Contributing

If you want to help with the development I'd be more than happy. The vast majority of the heavy lifting is done by MeiliSearch itself, but there is a TODO list...


### TODO

    * Faceting
    * Sort keys by boost value before creating an index
    * Search results

### Thanks

Thank you to the devs of [https://github.com/wagtail/wagtail-whoosh](Wagtail-Whoosh). Reading the code over there was the only way I could work out how Wagtail Search backends are supposed to work.
