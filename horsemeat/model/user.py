# vim: set expandtab ts=4 sw=4 filetype=python:

import logging
import textwrap
import weakref

import psycopg2.extras

log = logging.getLogger(__name__)

class UserInserter(object):

    def __init__(self, email_address, display_name, password=None,
        user_status='started registration'):

        self.email_address = email_address
        self.display_name = display_name
        self.password = password
        self.user_status = user_status

    @property
    def bound_variables(self):

        if self.password:

            return dict(
                email_address=self.email_address,
                display_name=self.display_name,
                password=self.password,
                person_status=self.user_status)

        else:

            return dict(
                email_address=self.email_address,
                display_name=self.display_name,
                person_status=self.user_status)

    @property
    def insert_query(self):

        if self.password:

            return textwrap.dedent("""
                insert into people
                (
                    email_address,
                    display_name,
                    salted_hashed_password,
                    person_status
                )
                values
                (
                    %(email_address)s,
                    %(display_name)s,
                    crypt(%(password)s, gen_salt('md5')),
                    %(person_status)s
                )
                returning person_id
                """)

        else:

            return textwrap.dedent("""
                insert into people
                (
                    email_address,
                    display_name,
                    person_status
                )
                values
                (
                    %(email_address)s,
                    %(display_name)s,
                    %(person_status)s
                )
                returning person_id
                """)

    def execute(self, dbconn):

        cursor = dbconn.cursor()

        cursor.execute(self.insert_query, self.bound_variables)

        return cursor.fetchone()



class PasswordUpdater(object):

    """
    pu = PasswordUpdater('matt@plus1.com', 'abcde')
    pu.update_password(pgconn)
    """

    def __init__(self, email_address, new_password):
        self.email_address = email_address
        self.new_password = new_password

    @property
    def update_query(self):

        return textwrap.dedent("""
            update people

            set salted_hashed_password =
            crypt(%(new_password)s, gen_salt('md5'))

            where email_address = (%(email_address)s)
            returning person_id
            """)

    @property
    def bound_variables(self):

        return dict(
            new_password=self.new_password,
            email_address=self.email_address)

    def execute(self, dbconn):

        cursor = dbconn.cursor()
        cursor.execute(self.update_query, self.bound_variables)

    # I love aliases.
    update_password = execute

def get_person_details(pgconn, person_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select (p.*)::people as p
        from people p
        where person_id = (%(person_id)s)
        """), {'person_id': person_id})

    return cursor.fetchone().p

def verify_credentials(pgconn, person_id, email_address, password):

    cursor = pgconn.cursor()

    # Later, consider returning some registered composite type.
    cursor.execute(textwrap.dedent("""
        select exists(
            select *
            from people
            where person_id = %(person_id)s
            and email_address = %(email_address)s
            and salted_hashed_password = crypt(
                %(password)s,
                salted_hashed_password)
        )
        """), {
            'person_id': person_id,
            'email_address': email_address,
            'password': password
        })

    return cursor.fetchone().exists

class PersonFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return Person(**d)


class Person(object):

    def __init__(self, person_id, email_address, salted_hashed_password,
        person_status, display_name, is_superuser, inserted, updated):

        self.person_id = person_id
        self.email_address = email_address
        self.salted_hashed_password = salted_hashed_password
        self.person_status = person_status
        self.display_name = display_name
        self.is_superuser = is_superuser
        self.inserted = inserted
        self.updated = updated

    def __repr__(self):

        return '<{0}.{1} ({2}:{3}) at 0x{4:x}>'.format(
            self.__class__.__module__,
            self.__class__.__name__,
            self.person_id,
            self.display_name,
            id(self))

    def __eq__(self, other):
        return self.person_id == getattr(other, 'person_id', -1)
