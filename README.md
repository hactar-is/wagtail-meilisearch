# Wagtail MeiliSearch

This is a (beta) Wagtail search backend for the [MeiliSearch](https://github.com/meilisearch/MeiliSearch) search engine.


## Installation

`poetry add wagtail_meilisearch` or `pip install wagtail_meilisearch`

## Configuration

See the [MeiliSearch docs](https://docs.meilisearch.com/guides/advanced_guides/installation.html#environment-variables-and-flags) for info on the values you want to add here.

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
* Implement boosting in the sort algorithm
* Write tests
* Performance improvements - particularly in the autocomplete query compiler which for some reason seems slower than the regular one.
* Implement stop words
* ~~Search results~~
* ~~Add support for the autocomplete api~~
* ~~Ensure we're getting results by relevance~~

### Thanks

Thank you to the devs of [Wagtail-Whoosh](https://github.com/wagtail/wagtail-whoosh). Reading the code over there was the only way I could work out how Wagtail Search backends are supposed to work.
