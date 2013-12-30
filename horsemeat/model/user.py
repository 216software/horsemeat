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

def get_candidate_read_only_users(pgconn, person_id, binder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select distinct people.*

        from people

        join people_clients_link
        on people_clients_link.person_id = people.person_id

        where client_uuid in (
            select client_uuid
            from people_clients_link
            where person_id = %(person_id)s
        )
        and people_clients_link.person_id != %(person_id)s

        and people_clients_link.person_id not in (
            select person_id
            from binder_read_only_users
            where binder_id = %(binder_id)s
        )

        and people_clients_link.person_id not in (
        select owner_id
        from binders
        where binder_id = %(binder_id)s
    )

    and people.person_status = 'confirmed'

    order by people.display_name

    """), {'person_id': person_id, 'binder_id': binder_id})

    return cursor

def get_candidate_auditors(pgconn, binder_id):

    """
    Return a list of people that could be added as an auditor
    to the binder with binder_id.

    Exclude from the list:

    *   this binder's owner
    *   any read-only users on this binder
    *   anyone who is already an auditor on this binder

    """

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""

        select (p2.*)::people as p

        from binders b

        join people_clients_link pcl
        on b.owner_id = pcl.person_id

        join people_clients_link pcl2
        on pcl.client_uuid = pcl2.client_uuid

        join people p2
        on pcl2.person_id = p2.person_id

        where b.binder_id = (%(binder_id)s)

        -- skip the owner of the binder
        and p2.person_id != b.owner_id

        -- skip read-only users
        and p2.person_id not in (
            select person_id
            from binder_read_only_users
            where binder_id = (%(binder_id)s)
        )

        -- skip other auditors
        and p2.person_id not in (
            select person_id
            from auditor_visibility
            where binder_id = (%(binder_id)s)
        )
        """), {'binder_id': binder_id})

    return cursor



class UserViz(object):

    def __init__(self, pgconn, binder_id, folder_id, person_id):

        self.pgconn = pgconn
        self.binder_id = binder_id
        self.folder_id = folder_id
        self.person_id = person_id

        self.cache = dict()

    def get_bundles_and_effective_files(self):

        if self.can_read_effective_files:

            from horsemeat.model import folder

            return folder.get_bundles_and_files(
                self.pgconn,
                self.binder_id,
                self.folder_id,
                effective=True).fetchall()

        else:
            return []

    def get_bundles_and_archived_files(self):

        if self.can_read_archived_files:

            from horsemeat.model import folder

            return folder.get_bundles_and_files(
                self.pgconn,
                self.binder_id,
                self.folder_id,
                effective=False).fetchall()

        else:

            return []

    @property
    def is_owner(self):

        if 'is_owner' in self.cache:
            return self.cache['is_owner']

        else:

            cursor = self.pgconn.cursor()

            cursor.execute(textwrap.dedent("""
                select exists(
                    select owner_id
                    from binders
                    where binder_id = %(binder_id)s
                    and owner_id = %(owner_id)s
                )"""),
                {'binder_id': self.binder_id, 'owner_id':
                self.person_id})

            self.cache['is_owner'] = cursor.fetchone().exists

            return self.cache['is_owner']

    @property
    def is_read_only_user_effective_files(self):

        return self.read_only_data \
        and self.read_only_data.access_effective_files

    @property
    def is_read_only_user_archived_files(self):

        return self.read_only_data \
        and self.read_only_data.access_archived_files

    @property
    def is_read_only_user(self):

        return self.is_read_only_user_effective_files \
        or self.is_read_only_user_archived_files


    @property
    def read_only_data(self):

        if 'read_only_data' in self.cache:
            return self.cache['read_only_data']

        else:

            cursor = self.pgconn.cursor()

            cursor.execute(textwrap.dedent("""
                select *
                from binder_read_only_users
                where binder_id = %(binder_id)s
                and person_id = %(person_id)s
                """),
                {
                    'binder_id': self.binder_id,
                    'person_id': self.person_id})

            if cursor.rowcount:
                self.cache['read_only_data'] = cursor.fetchone()

            else:
                self.cache['read_only_data'] = None

        return self.cache['read_only_data']

    @property
    def folder_visibility(self):

        if 'folder_visibility' in self.cache:
            return self.cache['folder_visibility']

        else:

            cursor = self.pgconn.cursor()

            cursor.execute(textwrap.dedent("""
                select (vs.*)::visibility_settings as vs
                from auditor_visibility av
                join visibility_settings vs
                on av.visibility_setting_id = vs.visibility_setting_id

                where binder_id = %(binder_id)s
                and folder_id = %(folder_id)s
                and person_id = %(person_id)s
                """),
                {'binder_id': self.binder_id,
                'folder_id': self.folder_id,
                'person_id': self.person_id})

            if cursor.rowcount:
                self.cache['folder_visibility'] = cursor.fetchone().vs

            else:
                self.cache['folder_visibility'] = False

            return self.folder_visibility


    @property
    def can_read_effective_files(self):

        f = self.get_folder_object()

        if f.is_front_page or f.is_a_log_folder:
            return

        return self.is_owner \
        or self.is_read_only_user_effective_files \
        or (
            self.folder_visibility
            and
            self.folder_visibility.can_read_effective_files)

    @property
    def can_read_archived_files(self):

        f = self.get_folder_object()

        if f.is_front_page or f.is_a_log_folder:
            return

        return self.is_owner \
        or self.is_read_only_user_archived_files \
        or (
            self.folder_visibility
            and
            self.folder_visibility.can_read_archived_files)

    @property
    def can_read_timeline(self):

        f = self.get_folder_object()

        if f.is_front_page or f.is_a_log_folder:
            return

        if self.is_owner:
            return True
        elif self.read_only_data.read_only_user_type == 'staff':
            return True
        elif self.read_only_data.read_only_user_type == 'monitor':
            return False


    @property
    def can_read_info(self):

        f = self.get_folder_object()

        if f.is_a_log_folder:
            return

        return self.is_owner \
        or self.is_read_only_user_effective_files \
        or (
            self.folder_visibility
            and
            self.folder_visibility.can_read_effective_files)

    @property
    def show_interactive_log_tab(self):

        f = self.get_folder_object()
        return f.is_a_log_folder

    def __repr__(self):

        return (
            '<UserViz (user {0}, binder {1}, folder {2})>'.format(
            self.person_id,
            self.binder_id,
            self.folder_id))

    @property
    def user_can_write(self):

        return self.is_owner

    @property
    def may_not_access_this_folder(self):

        if self.is_owner \
        or self.is_read_only_user \
        or self.folder_visibility:

            return False

        else:
            return True

    @property
    def may_access_this_folder(self):
        return not self.may_not_access_this_folder

    @property
    def can_upload_files(self):

        f = self.get_folder_object()

        if f.is_front_page or f.is_a_log_folder:
            return

        # Likely soon this will be way more complex.
        return self.is_owner


    @property
    def is_monitor(self):

        if 'is_monitor' in self.cache:
            return self.cache['is_monitor']

        else:

            cursor = self.pgconn.cursor()

            cursor.execute(textwrap.dedent("""
                select exists(
                    select *
                    from auditor_visibility
                    where binder_id = %(binder_id)s
                    and person_id = %(person_id)s
                )"""), {
                    'binder_id': self.binder_id,
                    'person_id': self.person_id
                })

            self.cache['is_monitor'] =  cursor.fetchone().exists

            # This is sort of fancy -- just tell python to rerun this
            # property, and upper-most if clause should now be true.
            return self.is_monitor

    @property
    def can_add_notes_to_file(self):

        """
        Later on, it's likely there will be more kinds of people that
        can add notes to the file than just the owner.
        """

        return self.is_owner

    @property
    def can_add_sticky_notes(self):

        return self.is_owner

    @property
    def can_view_sticky_notes(self):


        return self.is_owner or \
               self.read_only_data.read_only_user_type != 'monitor'


    def get_folders_I_monitor(self):

        from horsemeat.model import folder

        return folder.Folder.get_folders_I_monitor(
            self.pgconn,
            self.binder_id,
            self.person_id)

    def get_folder_IDs_I_monitor(self):
        return [row.f.folder_id for row in self.get_folders_I_monitor()]

    @property
    def should_not_access_this_binder(self):

        return not self.is_owner \
        and not self.is_read_only_user \
        and not self.is_monitor

    def get_folder_object(self):

        if 'folder_object' in self.cache:
            return self.cache['folder_object']

        else:

            from horsemeat.model import folder

            f = folder.get_folder_details(self.pgconn, self.folder_id)
            self.cache['folder_object'] = f

            return self.get_folder_object()




