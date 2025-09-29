class SuggestionRouter:
    """Route Suggestion model to 'suggests' DB for read/write/migrate."""
    app_label = 'core'
    model_name = 'Suggestion'
    db_name = 'suggests'

    def db_for_read(self, model, **hints):
        if model._meta.app_label == self.app_label and model.__name__ == self.model_name:
            return self.db_name
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == self.app_label and model.__name__ == self.model_name:
            return self.db_name
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == self.app_label and model_name == self.model_name.lower():
            return db == self.db_name
        return None