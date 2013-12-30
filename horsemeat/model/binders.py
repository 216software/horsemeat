# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import logging
import textwrap

import psycopg2.extras

log = logging.getLogger(__name__)

def get_my_binders(pgconn, owner_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select (b.*)::binders,
        (p.*)::people,
        brou2.number_of_monitors,
        brou.number_of_read_only_users

        from binders as b

        join people as p
        on p.person_id = owner_id

        left join (
             select binder_id, count(person_id) as number_of_read_only_users
             from binder_read_only_users
             where read_only_user_type = 'staff'
             group by binder_id
             ) brou
        on b.binder_id = brou.binder_id

        left join (
             select binder_id, count(person_id) as number_of_monitors
             from binder_read_only_users
             where read_only_user_type = 'monitor'
             group by binder_id
             ) brou2
        on b.binder_id = brou2.binder_id

        where b.owner_id = (%s)
        group by b.binder_id, p.person_id, brou2.number_of_monitors,
                 brou.number_of_read_only_users
        order by b.title"""),
        [owner_id])

    return cursor


def verify_user_owns_binder(pgconn, user_id, binder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select exists(
            select binders.binder_id
            from binders
            where binders.owner_id = (%s)
            and binders.binder_id = (%s)
        )"""),
        [user_id, binder_id])

    return cursor.fetchone().exists


def get_binder_details(pgconn, binder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select b.*,
        count(brou.person_id) as number_of_read_only_users
        from binders b
        left join binder_read_only_users brou
        on b.binder_id = brou.binder_id
        where b.binder_id = (%s)
        group by b.binder_id
        """),
        [binder_id])

    return cursor.fetchone()


def get_read_only_users(pgconn, binder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select people.*, binder_read_only_users.read_only_user_type
        from people
        join binder_read_only_users
        on people.person_id =  binder_read_only_users.person_id
        where binder_read_only_users.binder_id = (%s)
        """), [binder_id])

    return cursor


def insert_read_only_user(pgconn, binder_id, person_id,
                          read_only_user_type='staff'):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        insert into binder_read_only_users
        (binder_id, person_id, read_only_user_type)
        values
        (%s, %s, %s)
        """), [binder_id, person_id, read_only_user_type])


def get_my_read_only_binders(pgconn, person_id,
                            read_only_user_type='staff'):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select (b.*)::binders,
        (p.*)::people

        from binders b

        join binder_read_only_users brou
        on b.binder_id = brou.binder_id
        and brou.person_id = %(person_id)s

        join people p
        on b.owner_id = p.person_id

        where brou.read_only_user_type = %(read_only_user_type)s

        group by b.binder_id, p.person_id

        """), {'person_id': person_id,
               'read_only_user_type':read_only_user_type})

    return cursor


def verify_user_can_read_binder(pgconn, binder_id, person_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select exists(
            select person_id
            from binder_read_only_users
            where binder_id = (%s)
            and person_id = (%s)
        )"""), [binder_id, person_id])

    return cursor.fetchone().exists


def get_institutional_binders(pgconn, person_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select (b.*)::binders
        from clients c

        join people_clients_link pcl
        on c.client_uuid = pcl.client_uuid

        join binders b
        on c.institution_binder_id = b.binder_id

        where pcl.person_id = (%(person_id)s)
        and c.institution_binder_id is not NULL
        """), {'person_id': person_id})

    return cursor

class Binder(object):

    def __init__(self, binder_id, owner_id, title, description,
        archived, inserted, updated, binder_template_id):

        self.binder_id = binder_id
        self.owner_id = owner_id
        self.title = title
        self.description = description
        self.archived = archived
        self.inserted = inserted
        self.updated = updated
        self.binder_template_id = binder_template_id

    @classmethod
    def look_up_redirect_folder_id(cls, pgconn, binder_id):

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select coalesce(
                bt.redirect_to_this_folder_id,
                bt.root_folder_id) as redirect_to_this_folder_id

            from binders b

            join binder_templates bt
            on b.binder_template_id = bt.binder_template_id

            where b.binder_id = %(binder_id)s
            """), {'binder_id': binder_id})

        return cursor.fetchone().redirect_to_this_folder_id

class BinderFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return Binder(**d)

class BinderTemplate(object):

    def __init__(self, binder_template_id, title, hidden, description,
        root_folder_id, inserted, updated, redirect_to_this_folder_id):

        self.binder_template_id = binder_template_id
        self.title = title
        self.hidden = hidden
        self.description = description
        self.root_folder_id = root_folder_id
        self.inserted = inserted
        self.updated = updated
        self.redirect_to_this_folder_id = redirect_to_this_folder_id

    @classmethod
    def get_all_binder_templates(cls, pgconn):

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select (binder_templates.*)::binder_templates as bt
            from binder_templates
            where hidden = false
            order by title
            """))

        return cursor

class BinderTemplateFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return BinderTemplate(**d)


def add_everyone_as_read_only_user(pgconn, binder_id, client_uuid,
                                   read_only_user_type='staff'):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        insert into binder_read_only_users
        (binder_id, person_id, read_only_user_type)

        select %(binder_id)s, pcl.person_id, %(read_only_user_type)s
        from people_clients_link pcl

        where pcl.client_uuid = %(client_uuid)s

        -- Don't try to add people already in the list of read-only
        -- users for this binder.
        and pcl.person_id not in (
            select person_id
            from binder_read_only_users
            where binder_id = %(binder_id)s
        )

        -- Do not add the binder owner as a read-only user!
        and pcl.person_id not in (
            select owner_id
            from binders
            where binder_id = %(binder_id)s
        )
        """), {'binder_id': binder_id, 'client_uuid': client_uuid,
               'read_only_user_type':read_only_user_type})

    log.info("Just added {0} people from client {1} as read-only "
        "users to binder {2}.".format(
            cursor.rowcount,
            client_uuid,
            binder_id))

def verify_is_monitor(pgconn, binder_id, folder_id, person_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select (vs.*)::visibility_settings as vs
        from auditor_visibility av
        join visibility_settings vs
        on av.visibility_setting_id = vs.visibility_setting_id
        where av.binder_id = %(binder_id)s
        and av.folder_id = %(folder_id)s
        and av.person_id = %(person_id)s
        """), {'binder_id': binder_id, 'folder_id': folder_id,
        'person_id': person_id})

    if cursor.rowcount:
        return cursor.fetchone().vs

def get_binders_I_monitor(pgconn, person_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select distinct
        (b.*)::binders as b,
        (p.*)::people as p

        from binders b

        join auditor_visibility av
        on b.binder_id = av.binder_id

        join people p
        on b.owner_id = p.person_id

        where av.person_id = %(person_id)s
        """), {'person_id': person_id})

    return cursor

