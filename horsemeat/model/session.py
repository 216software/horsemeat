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
            insert into webapp_sessions
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

            returning session_uuid""")

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

def extract_session_uuid(HTTP_COOKIE, secret):

    """
    Return the session ID if everything works out.
    """

    log.debug('HTTP_COOKIE is %s' % HTTP_COOKIE)
    log.debug('secret is %s' % secret)

def set_project_id_in_session(pgconn, session_uuid, project_id):

    cursor = get_one_session_namespace(pgconn, session_uuid, 'global')

    if cursor.rowcount:

        session_data = cursor.fetchone().session_data
        session_data['project_id'] = str(project_id)

        cursor.execute(textwrap.dedent("""
            update webapp_session_data
            set session_data = (%s)
            where session_uuid = (%s)
            and namespace = (%s)
            """), [session_data, session_uuid, 'global'])

    else:

        # If a webapp_session_data row doesn't exist, insert one.

        session_data = dict({'project_id': str(project_id)})

        cursor.execute(textwrap.dedent("""
            insert into webapp_session_data
            (session_uuid, namespace, session_data)
            values
            (%s, %s, %s)
            """), [session_uuid, 'global', session_data])


def get_all_session_namespaces(pgconn, session_uuid):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select session_uuid, namespace, session_data, inserted,
        updated

        from webapp_session_data

        where session_uuid = (%s)
        """), [session_uuid])

    d = dict()

    for session_uuid, namespace, session_data, inserted, updated in cursor:
        d[namespace] = session_data

    return d


def get_one_session_namespace(pgconn, session_uuid, namespace):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select session_uuid, namespace, session_data, inserted,
        updated

        from webapp_session_data

        where session_uuid = (%s)
        and namespace = (%s)
        """), [session_uuid, namespace])

    return cursor

def set_binder_id_in_session(pgconn, session_uuid, binder_id):

    cursor = get_one_session_namespace(pgconn, session_uuid, 'global')

    if cursor.rowcount:

        session_data = cursor.fetchone().session_data
        session_data['binder_id'] = str(binder_id)

        cursor.execute(textwrap.dedent("""
            update webapp_session_data
            set session_data = (%s)
            where session_uuid = (%s)
            and namespace = (%s)
            """), [json.dumps(session_data), session_uuid, 'global'])

    else:

        # If a webapp_session_data row doesn't exist, insert one.

        session_data = dict({'binder_id': str(binder_id)})

        cursor.execute(textwrap.dedent("""
            insert into webapp_session_data
            (session_uuid, namespace, session_data)
            values
            (%s, %s, %s)
            """), [session_uuid, 'global', json.dumps(session_data)])


class SessionFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return Session(**d)

class Session(object):

    def __init__(self, session_uuid, expires, person_id, news_message,
        redirect_to_url, inserted, updated):

        self.session_uuid = session_uuid
        self.expires = expires
        self.person_id = person_id
        self.news_message = news_message
        self.redirect_to_url = redirect_to_url
        self.inserted = inserted
        self.updated = updated

    def maybe_update_session_expires_time(self, pgconn):

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            update webapp_sessions
            set expires = default
            where session_uuid = (%(session_uuid)s)
            and expires > current_timestamp
            returning expires
        """), {'session_uuid': self.session_uuid})

        if cursor.rowcount:
            return cursor.fetchone().expires


    def retrieve_session_data(self, pgconn, namespace):

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select session_data
            from webapp_session_data
            where session_uuid = %s
            and namespace = %s
            """), [self.session_uuid, namespace])

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
                delete from webapp_session_data
                where session_uuid = %s
                and namespace = %s
                """), [self.session_uuid, namespace])

        return session_data

    @classmethod
    def maybe_start_new_session_after_checking_email_and_password(cls,
        pgconn, email_address, password):

        """
        If the email address and password match a row in the people
        table, insert a new session and return it.
        """

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            insert into webapp_sessions
            (person_id)
            select person_id
            from people
            where email_address = %(email_address)s
            and salted_hashed_password = crypt(
                %(password)s,
                salted_hashed_password)
            and person_status = 'confirmed'
            returning (webapp_sessions.*)::webapp_sessions as gs
            """), {
                "email_address": email_address,
                "password": password})


        if cursor.rowcount:
            return cursor.fetchone().gs

    @property
    def __jsondata__(self):
        return self.__dict__
