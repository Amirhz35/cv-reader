"""
Database routers for dual database setup.
Routes auth/user models to MySQL, CV/data models to MongoDB.
"""

class DatabaseRouter:
    """
    A router to control all database operations on models in the
    auth and contenttypes applications.
    """

    def db_for_read(self, model, **hints):
        """
        Attempts to read auth and contenttypes models go to default (MySQL).
        """
        if model._meta.app_label in ['auth', 'contenttypes', 'sessions', 'admin']:
            return 'default'
        return 'mongodb'

    def db_for_write(self, model, **hints):
        """
        Attempts to write auth and contenttypes models go to default (MySQL).
        """
        if model._meta.app_label in ['auth', 'contenttypes', 'sessions', 'admin']:
            return 'default'
        return 'mongodb'

    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations if a model in the auth or contenttypes apps is
        involved. Deny cross-database relations otherwise.
        """
        if (
            obj1._meta.app_label in ['auth', 'contenttypes', 'sessions', 'admin'] or
            obj2._meta.app_label in ['auth', 'contenttypes', 'sessions', 'admin']
        ):
            return True
        return obj1._meta.app_label == obj2._meta.app_label

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Make sure the auth and contenttypes apps only appear in the
        'default' database.
        """
        if app_label in ['auth', 'contenttypes', 'sessions', 'admin']:
            return db == 'default'
        return db == 'mongodb'
