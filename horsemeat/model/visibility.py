# vim: set expandtab ts=4 sw=4 syntax=python fileencoding=utf8:

import logging
import textwrap

import psycopg2.extras

class VisibilitySettingsFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return VisibilitySetting(**d)

class VisibilitySetting(object):

    def __init__(self, visibility_setting_id, title, description,
        inserted, updated):

        self.visibility_setting_id = visibility_setting_id
        self.title = title
        self.description = description
        self.inserted = inserted
        self.updated = updated

    @classmethod
    def all(cls, pgconn):

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select (vs.*)::visibility_settings as vs
            from visibility_settings vs
            order by title
            """))

        return cursor

    @property
    def can_read_effective_files(self):

        return self.title in set([
            'See effective files only',
            'See effective files and archived files',
        ])

    @property
    def can_read_archived_files(self):

        return self.title in set([
            'See effective files and archived files',
        ])
