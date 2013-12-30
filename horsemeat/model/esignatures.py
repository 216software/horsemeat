# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import logging
import textwrap

import psycopg2.extras

log = logging.getLogger(__name__)

class BundleEsignatureFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return BundleEsignature(**d)

class BundleEsignature(object):

    def __init__(self, bundle_id, person_id, extra_notes,
        inserted, updated):

        self.bundle_id = bundle_id
        self.person_id = person_id
        self.extra_notes = extra_notes
        self.inserted = inserted
        self.updated = updated

def insert_esignature(pgconn, file_id, person_id, extra_notes=None):

    if extra_notes:

        qry = textwrap.dedent("""
            insert into esignatures
            (file_id, person_id, extra_notes)
            values
            (%(file_id)s, %(person_id)s, %(extra_notes)s)
            """)

        bound_vars = {
            'file_id': file_id,
            'person_id': person_id,
            'extra_notes': extra_notes,
        }

    else:

        qry = textwrap.dedent("""
            insert into esignatures
            (file_id, person_id)
            values
            (%(file_id)s, %(person_id)s)
            """)

        bound_vars = {
            'file_id': file_id,
            'person_id': person_id,
        }

    cursor = pgconn.cursor()

    cursor.execute(qry, bound_vars)

def insert_bundle_esignature(pgconn, bundle_id, person_id,
    extra_notes=None):

    qry = textwrap.dedent("""
        insert into bundle_esignatures
        (bundle_id, person_id, extra_notes)
        values
        (%(bundle_id)s, %(person_id)s, nullif(%(extra_notes)s, ''))
        """)

    bound_vars = {
        'bundle_id': bundle_id,
        'person_id': person_id,
        'extra_notes': extra_notes,
    }

    cursor = pgconn.cursor()

    cursor.execute(qry, bound_vars)

    return cursor


def build_esignatures_dict(pgconn, bundle_ids):

    cleaned_up_bundle_ids = [int(x) for x in bundle_ids]

    cursor = pgconn.cursor()

    qry = textwrap.dedent("""
        select
        be.bundle_id,

        array_agg((p.*)::people) as signers

        from bundle_esignatures be

        join people p
        on be.person_id = p.person_id

        where be.bundle_id = any(%(bundle_ids)s)

        group by be.bundle_id
        """)

    cursor.execute(qry, {'bundle_ids': cleaned_up_bundle_ids})

    d = dict()

    for row in cursor:
        d[row.bundle_id] = row.signers

    return d
