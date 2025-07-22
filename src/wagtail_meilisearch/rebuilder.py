import sys

from .index import DummyModelIndex
from .utils import get_index_label


class MeiliSearchRebuilder:
    def __init__(self, model_index):
        self.index = model_index
        self.uid = get_index_label(self.index.model)
        self.dummy_index = DummyModelIndex()

    def start(self):
        """
        Starts the rebuild process for the search index.

        This method implements three strategies for rebuilding the index:
        - 'hard': Deletes every document in the index and adds them anew.
        - 'soft': Performs an "add or update" for each document.
        - 'delta': Only updates documents that have been saved in the last X amount of time.

        Returns:
            The appropriate index object for further operations.
        """
        model = self.index.model
        if self.index.model._meta.label in self.index.backend.skip_models:
            sys.stdout.write(f'SKIPPING: {self.index.model._meta.label}\n')
            return self.dummy_index

        strategy = self.index.backend.update_strategy

        if strategy == 'soft' or strategy == 'delta':
            # Soft update strategy
            index = self.index.backend.get_index_for_model(model)
        else:
            # Hard update strategy
            old_index = self.index.backend.get_index_for_model(model)
            old_index.delete_all_documents()

        model = self.index.model
        index = self.index.backend.get_index_for_model(model)
        return index

    def finish(self):
        pass
