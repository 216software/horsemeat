# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import logging
import textwrap

import psycopg2.extras

log = logging.getLogger(__name__)

__all__ = ['BundleFactory', 'BundleEsignatureFactory']

class BundleFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return Bundle(**d)

class Bundle(object):

    def __init__(self, bundle_id, binder_id, bundle_universal_id,
        folder_id,
        filename, comment, bundle_title, pdf_version, doc_version,
        created_by,
        inserted, updated):

        self.bundle_id = bundle_id
        self.bundle_universal_id = bundle_universal_id
        self.binder_id = bundle_id
        self.folder_id = folder_id
        self.filename = filename
        self.comment = comment
        self.bundle_title = bundle_title
        self.pdf_version = pdf_version
        self.doc_version = doc_version
        self.created_by = created_by
        self.inserted = inserted
        self.updated = updated

    @classmethod
    def by_bundle_id(cls, pgconn, bundle_id):

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select (b.*)::bundles as bundle
            from bundles b
            where b.bundle_id = (%s)
            """), [bundle_id])

        return cursor.fetchone().bundle


    def make_effective(self, pgconn, person_id):

        """
        To deal with new design, we're going to use a concept
        of keeping track of effective start and end.

        TODO:If this bundle is already effective (no end date)
        then we shouldn't do anything, as we'll need to
        make something uneffective before it can be made
        effective again
        """

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""

        insert into bundle_effective_links
        (bundle_id, person_id, effective_range)
        values
        (%s , %s, tstzrange(now(),'infinity'))
        """), [self.bundle_id, person_id])

        return


    def close_effective(self, pgconn):

        """

        We're going to close all bundle_effective_links
        that have our bundle id (there should really be
        only one, probably)

        Updating a record's effective_range to
        an upper bound of 'now' will close off
        the record.

        So query where bundle id = me and now is contained
        in effective range
        """


        log.debug("Closing the effectiveness of bundle {0}". \
                   format(self.bundle_id))

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
        update bundle_effective_links

        set effective_range = tstzrange(lower(effective_range), now())

        where bundle_id = (%s) and
        now() <@ effective_range ;

        """), [self.bundle_id])

    def make_historical(self, pgconn, person_id):

        """
        To deal with new design, we're going to use a concept
        of keeping track of effective start and end.

        """


        log.debug("Making bundle {0} historical".format(
                                                 self.bundle_id))

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""

        insert into bundle_history_links
        (bundle_id, person_id, history_range)
        values
        (%s , %s, tstzrange(now(),'infinity'))
        """), [self.bundle_id, person_id])

        return

    def close_historical(self, pgconn):

        """

        We're going to close all bundle_history_links
        that have our bundle id (there should really be
        only one, probably) and aren't closed (now is within the range)

        """


        log.debug("Closing the historicalness of bundle {0}". \
                   format(self.bundle_id))

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
        update bundle_history_links

        set history_range = tstzrange(lower(history_range), now())

        where bundle_id = (%s) and
        now() <@ history_range ;

        """), [self.bundle_id])

    @staticmethod
    def change_a_bundles_status(pgconn,
                                bundle_id,
                                new_status, person_id):

        """

        """

        #First close all open statuses (ie upper bound infinity)
        cursor = pgconn.cursor()
        cursor.execute(textwrap.dedent("""
            update bundle_status_link

            set time_range = tstzrange(lower(time_range),
                                             now())
            where bundle_id = (%s) and
            now() <@ time_range ;

        """), [bundle_id])


        #Then insert a new line
        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""

        insert into bundle_status_link
        (bundle_id, bundle_status, person_id, time_range)
        values
        (%s , %s, %s, tstzrange(now(),'infinity'))
        """), [bundle_id, new_status, person_id])



class BundleEsignatureFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return BundleEsignature(**d)

class BundleEsignature(object):

    def __init__(self, bundle_id, person_id, extra_notes, inserted,
        updated):

        self.bundle_id = bundle_id
        self.person_id = person_id
        self.extra_notes = extra_notes
        self.inserted = inserted
        self.updated = updated
