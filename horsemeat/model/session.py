# vim: set expandtab ts=4 sw=4 filetype=python:

import json
import logging
import textwrap

import psycopg2.extras

log = logging.getLogger(__name__)

class SessionInserter(object):

    def __init__(self, person_id, news_message=None, redirect_to_this_url=None):

        self.person_id = person_id
        self.news_message = news_message
        self.redirect_to_this_url = redirect_to_this_url

    @property
    def insert_query(self):

        return textwrap.dedent("""
            insert into horsemeat_sessions
            (
                person_id,
                news_message,
                redirect_to_url
            )

            values
            (
                %(person_id)s,
                %(news_message)s,
                %(redirect_to_this_url)s
            )

            returning session_id""")

    @property
    def bound_variables(self):

        return dict(
            person_id=self.person_id,
            news_message=self.news_message,
            redirect_to_this_url=self.redirect_to_this_url)

    def execute(self, dbconn):

        cursor = dbconn.cursor()

        cursor.execute(self.insert_query, self.bound_variables)

        return cursor.fetchone()

def extract_session_id(HTTP_COOKIE, secret):

    """
    Return the session ID if everything works out.
    """

    log.debug('HTTP_COOKIE is %s' % HTTP_COOKIE)
    log.debug('secret is %s' % secret)

def set_project_id_in_session(pgconn, session_id, project_id):

    cursor = get_one_session_namespace(pgconn, session_id, 'global')

    if cursor.rowcount:

        session_data = cursor.fetchone().session_data
        session_data['project_id'] = str(project_id)

        cursor.execute(textwrap.dedent("""
            update horsemeat_session_data
            set session_data = (%s)
            where session_id = (%s)
            and namespace = (%s)
            """), [session_data, session_id, 'global'])

    else:

        # If a horsemeat_session_data row doesn't exist, insert one.

        session_data = dict({'project_id': str(project_id)})

        cursor.execute(textwrap.dedent("""
            insert into horsemeat_session_data
            (session_id, namespace, session_data)
            values
            (%s, %s, %s)
            """), [session_id, 'global', session_data])


def get_all_session_namespaces(pgconn, session_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select session_id, namespace, session_data, inserted,
        updated

        from horsemeat_session_data

        where session_id = (%s)
        """), [session_id])

    d = dict()

    for session_id, namespace, session_data, inserted, updated in cursor:
        d[namespace] = session_data

    return d


def get_one_session_namespace(pgconn, session_id, namespace):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select session_id, namespace, session_data, inserted,
        updated

        from horsemeat_session_data

        where session_id = (%s)
        and namespace = (%s)
        """), [session_id, namespace])

    return cursor

def set_binder_id_in_session(pgconn, session_id, binder_id):

    cursor = get_one_session_namespace(pgconn, session_id, 'global')

    if cursor.rowcount:

        session_data = cursor.fetchone().session_data
        session_data['binder_id'] = str(binder_id)

        cursor.execute(textwrap.dedent("""
            update horsemeat_session_data
            set session_data = (%s)
            where session_id = (%s)
            and namespace = (%s)
            """), [json.dumps(session_data), session_id, 'global'])

    else:

        # If a horsemeat_session_data row doesn't exist, insert one.

        session_data = dict({'binder_id': str(binder_id)})

        cursor.execute(textwrap.dedent("""
            insert into horsemeat_session_data
            (session_id, namespace, session_data)
            values
            (%s, %s, %s)
            """), [session_id, 'global', json.dumps(session_data)])


class SessionFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return Session(**d)

class Session(object):

    def __init__(self, session_id, expires, person_id, news_message,
        redirect_to_url, inserted, updated):

        self.session_id = session_id
        self.expires = expires
        self.person_id = person_id
        self.news_message = news_message
        self.redirect_to_url = redirect_to_url
        self.inserted = inserted
        self.updated = updated

    def maybe_update_session_expires_time(self, pgconn):

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            update horsemeat_sessions
            set expires = default
            where session_id = (%(session_id)s)
            and expires > current_timestamp
            returning expires
        """), {'session_id': self.session_id})

        if cursor.rowcount:
            return cursor.fetchone().expires


    def retrieve_session_data(self, pgconn, namespace):

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select session_data
            from horsemeat_session_data
            where session_id = %s
            and namespace = %s
            """), [self.session_id, namespace])

        if cursor.rowcount:
            return cursor.fetchone().session_data

    def pop_session_data(self, pgconn, namespace):

        """
        Retrieve and then delete the session data.
        """

        session_data = self.retrieve_session_data(pgconn, namespace)

        if session_data:

            cursor = pgconn.cursor()

            cursor.execute(textwrap.dedent("""
                delete from horsemeat_session_data
                where session_id = %s
                and namespace = %s
                """), [self.session_id, namespace])

        return session_data
