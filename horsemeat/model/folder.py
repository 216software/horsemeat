# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import collections
import logging
import glob
from hashlib import sha1
import hmac
import os
import textwrap
import time

import psycopg2.extras

from horsemeat import configwrapper

log = logging.getLogger(__name__)

def destroy_all_folders(pgconn):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        delete from folders
    """))

    cursor.execute(
        "alter sequence folders_folder_id_seq restart with 1")

    log.info('Just deleted all the folders and reset the sequence!')


def load_folder_structure_from_dropbox(
    cw,
    root_path,
    parent_folder_id=None,
    indent_level=0,
    has_internet_connection=True):

    folders = [x for x in os.listdir(root_path)
        if os.path.isdir(os.path.join(root_path, x))]

    inserted_folder_ids = []

    for f in sorted(folders):

        if f.upper().startswith('I_AM_SPECIAL'):
            continue
            # handle_special_folder(cw, os.path.join(root_path, f))

        else:

            cursor = cw.get_pgconn().cursor()

            cursor.execute(textwrap.dedent("""
                insert into folders
                (parent_folder_id, folder_title)
                values
                (%s, %s)
                returning folder_id
                """), [parent_folder_id, f])

            folder_id = cursor.fetchone().folder_id

            inserted_folder_ids.append(folder_id)

            try:

                update_folder(cw, folder_id, os.path.join(root_path, f),
                    has_internet_connection=has_internet_connection)

            except Exception as ex:
                log.exception(ex)

                log.error('this is the bad folder: {0}'.format(

                    os.path.join(root_path, f)))

                raise

            load_folder_structure_from_dropbox(
                cw,
                os.path.join(root_path, f),
                str(folder_id),
                indent_level=indent_level+4,
                has_internet_connection=has_internet_connection)

    return inserted_folder_ids

def handle_special_folder(cw, path_to_special_folder):

    #cloudconn = cw.make_new_cloudfile_connection()
    pyrax = cw.get_pyrax_connection()
    # This returns existing container if container already exists.
    training_files_container = pyrax.cloudfiles.create_container(
        'training_files')

    training_pdf_files = glob.glob('{0}/*.pdf'.format(
        path_to_special_folder))

    for f in training_pdf_files:

        file_name = os.path.basename(f)
        #obj = training_files_container.create_object(file_name)
        #obj.load_from_filename(f)
        obj = training_files_container.upload_file(f)

        cursor = cw.get_pgconn().cursor()

        cursor.execute(textwrap.dedent("""
            insert into training_guides
            (title)
            values
            (%s)
            """), [file_name])


def clean_string_or_null(x):

    cleaned = [
        line.strip().replace("\x92", "'").replace("\x93", '"').replace("\x94", '"')

        for line in x if line.strip()]

    if cleaned:
        return '  '.join(cleaned)


def update_folder(cw, folder_id, current_path,
    has_internet_connection=True):

    info_file_path = os.path.join(current_path, 'Info.txt')

    if os.path.exists(info_file_path):

        file_guts = open(info_file_path).read()

        d = parse_info_file(file_guts)

        folder_format = parse_format_section(d['FORMAT'])

        cursor = cw.get_pgconn().cursor()

        bound_vars = {
            'description': clean_string_or_null(d['DESCRIPTION']),
            'guidance': clean_string_or_null(d['GUIDANCE']),
            'instructions': clean_string_or_null(d['INSTRUCTIONS']),
            'raw_info': clean_string_or_null(file_guts),
            'folder_format': folder_format,
            'folder_id': folder_id}

        cursor.execute(textwrap.dedent("""
            update folders
            set
            description = (%(description)s),
            guidance = (%(guidance)s),
            instructions = (%(instructions)s),
            raw_info = (%(raw_info)s),
            folder_format = (%(folder_format)s)

            where folder_id = (%(folder_id)s)
            """), bound_vars)

        template_file_names = folder_format.get('Template_File', '[]')

        try:
            x = eval(template_file_names)

        # Catch template_file_names that are just a single file.
        except (NameError, SyntaxError) as ex:
            log.error('Failed to eval {0}.'.format(template_file_names))
            x = template_file_names

        if isinstance(x, basestring):
            upload_template_file(cw, folder_id, os.path.join(current_path, x))

        elif isinstance(x, collections.Iterable):

            for tf in x:
                upload_template_file(cw, folder_id, os.path.join(current_path, tf.strip()))


def get_top_folders(pgconn):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select folder_id, folder_title, description, guidance,
        instructions, folder_format, raw_info, inserted, updated
        from folders
        where parent_folder_id is NULL
        order by folder_title
        """))

    return cursor

def get_child_folders(pgconn, folder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select folder_id, folder_title, description, guidance,
        instructions, folder_format, raw_info, inserted, updated
        from folders
        where parent_folder_id = (%s)
        order by folder_title
    """), [folder_id])

    return cursor

def get_child_folders_with_their_uploads(pgconn, binder_id, parent_folder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select f.folder_id, f.parent_folder_id, f.folder_title,
        f.folder_format,

        nullif(
            array_agg((uf.*)::uploaded_files),
            array[NULL]::uploaded_files[])
        as uploaded_files

        from folders f

        left join uploaded_files uf
        on f.folder_id = uf.folder_id
        and uf.binder_id = (%(binder_id)s)

        where f.parent_folder_id = (%(parent_folder_id)s)

        group by f.folder_id, f.parent_folder_id, f.folder_title

        order by f.folder_title
        """), {
            'parent_folder_id': parent_folder_id,
            'binder_id': binder_id,
        })

    return cursor

class UploadedFileCompositeFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return UploadedFile(**d)



def get_folder_details(pgconn, folder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select (f.*)::folders as f
        from folders f

        where folder_id = (%s)

        order by folder_title
    """), [folder_id])

    if cursor.rowcount:
        return cursor.fetchone().f

def get_binder_folder_details(pgconn, binder_id, folder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select binder_id, folder_id, notes, notes_draft, inserted,
        updated
        from binder_folder_details
        where binder_id = (%s)
        and folder_id = (%s)
    """), [binder_id, folder_id])

    return cursor.fetchone()

def get_uploaded_files(pgconn, binder_id, folder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select u.file_id, u.owner_id,
        u.binder_id, u.folder_id, u.filename,
        u.path_to_word, u.path_to_pdf,
        u.uploader_comment, u.inserted, u.updated,
        count(s.signature_id)

        from uploaded_files as u

        left join uploaded_signatures as s
        on s.file_id = u.file_id

        where binder_id = (%s)
        and folder_id = (%s)
        group by u.file_id, u.owner_id,
        u.binder_id, u.folder_id, u.filename,
        u.path_to_word, u.path_to_pdf,
        u.uploader_comment, u.inserted, u.updated

        order by u.inserted desc

    """), [binder_id, folder_id])

    return cursor

def get_uploaded_files_count(pgconn, binder_id, folder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select count(*) as count
        from
        uploaded_files
        where binder_id = (%s)
        and folder_id = (%s)"""),
        [binder_id, folder_id])

    return cursor

def build_uploaded_bundle_signature_dict(pgconn, bundle_ids):

    cleaned_up_bundle_ids = [int(x) for x in bundle_ids]

    cursor = pgconn.cursor()

    qry = textwrap.dedent("""

        select
        ubs.bundle_id,

        array_agg((bsig.*)::bundle_signatures_with_signatory_names)
        as signers

        from uploaded_bundle_signatures ubs
        join bundle_signatures_with_signatory_names bsig
        on ubs.signature_uuid = bsig.signature_uuid

        where ubs.bundle_id = any(%(bundle_ids)s)

        group by ubs.bundle_id

       """)

    cursor.execute(qry, {'bundle_ids': cleaned_up_bundle_ids})

    d = dict()

    for row in cursor:
        d[row.bundle_id] = row.signers

    return d



def get_uploaded_files_with_signatures(pgconn, binder_id,
                                               folder_id,
                                               owner_id,
                                               limit=5,
                                               offset=0):

    """

    limit and offset are not currently implemented

    """

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""

        with pretty_file_id_table as
        (
        select ug.*,
        (ug.binder_id || '-' || ug.folder_id || '-' || row_number() over (order by ug.inserted)) as file_display_id
        from uploaded_files as ug
        where ug.owner_id = (%(owner_id)s)
        and ug.folder_id = (%(folder_id)s)
        and ug.binder_id = (%(binder_id)s)
        )

        select (uf.*)::uploaded_files as uploaded_file,
                nullif(
                    array_agg((s.*)::signatures_with_signatories),
                    array[NULL]::signatures_with_signatories[])
                as signatures,
                nullif(
                    array_agg((es.*)::esignatures),
                    array[NULL]::esignatures[])
                as esignatures,
                ff.file_display_id as fancy_file_id

                from uploaded_files as uf
                left join signatures_with_signatories as s
                on s.file_id = uf.file_id
                left join esignatures es
                on uf.file_id = es.file_id
                left join pretty_file_id_table as ff
                on ff.file_id = uf.file_id
                where uf.folder_id = (%(folder_id)s)
                and uf.binder_id = (%(binder_id)s)
                group by uploaded_file, uf.inserted, fancy_file_id
                order by uf.inserted desc


        """), {
            'folder_id' : folder_id,
            'binder_id' : binder_id,
            'limit' : limit,
            'offset' : offset,
            'owner_id' : owner_id
        })
    return cursor


def get_activity_log(pgconn, binder_id, folder_id):

    """

    Get all activity for a given folder and binder.

    Activity is when a user makes a bundle effective
    or moves a bundle to history. It also tells us
    who did the action.

    Also notes to file.

    Also signatures.

    """

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""


select (coalesce(n.action_type, '') || coalesce(b.action_type, '') || coalesce(bss.action_type, '')) as action_type,
           (coalesce(b.action_time::text, '') || coalesce(n.action_time::text, '') || coalesce(bss.action_time::text,''))::timestamp as action_date,
           (coalesce(b.display_name::text, '') || coalesce(n.display_name::text, '')) as display_name,
           b.bundle_status, b.bundle_universal_id,
           b.filename, b.rackspace_pdf,
           n.notes_to_file_universal_id,
           bss.signers,
           bss.bundle as sig_bundle
           from
              (
              select 'bundle'::text as action_type,
              lower(bsl.time_range) as action_time,
              p.display_name, bsl.bundle_status, (rfp.*)::rackspace_files as rackspace_pdf,
              bundles.bundle_universal_id, bundles.filename
              from bundles
              inner join bundle_status_link as bsl
              on bundles.bundle_id = bsl.bundle_id
              left join rackspace_files as rfp
              on rfp.object_name = bundles.pdf_version
              inner join people as p on p.person_id = created_by
              where bundles.folder_id = %(folder_id)s and bundles.binder_id = %(binder_id)s) b
              full join
              (select 'note'::text as action_type,
               notes_to_file.inserted as action_time,
               notes_to_file.notes_to_file_universal_id,
               p.display_name from notes_to_file
               inner join people as p on p.person_id = owner_id
                 where notes_to_file.folder_id = %(folder_id)s
                 and notes_to_file.binder_id = %(binder_id)s
                 ) n
                 on n.action_time = b.action_time
              full join
              (
                select 'signature'::text as action_type,
                       b1.signers || b2.signers as signers,
                       (bund.*)::bundles as bundle,
                       (coalesce(b1.inserted::text,'') || coalesce(b2.inserted::text,''))::timestamp as action_time
                from

                (select array_agg(p.display_name) as signers,
                     be.inserted as inserted,
                     b.bundle_id
                from bundle_esignatures as be
                join people as p on p.person_id = be.person_id
                join bundles as b on b.bundle_id = be.bundle_id
                group by be.inserted, b.bundle_id) b1

                full join
                (
                select bss.inserted as inserted,
                b.bundle_id,
                bss.signers
                from bundle_signatures_with_signatory_names bss
                inner join bundles as b on b.bundle_id = bss.bundle_id
                ) b2 on b2.inserted = b1.inserted

                left join bundles as bund
                on bund.bundle_id = (coalesce(b1.bundle_id::text, '') || coalesce(b2.bundle_id::text, ''))::integer

                where bund.folder_id = %(folder_id)s
                and bund.binder_id = %(binder_id)s
              ) bss on bss.action_time = b.action_time
              order by action_date desc;



    """), {'folder_id':folder_id,
           'binder_id':binder_id})

    return cursor


def get_bundles_and_files(pgconn, binder_id, folder_id, effective=True):

    """

    Get all bundles and their associated files for
    a given folder and binder.

    Default, returns all effective files. If effective files is false,
    then give us the historical files

    """

    cursor = pgconn.cursor()

    bundle_status = 'effective' if effective else 'archived'

    cursor.execute(textwrap.dedent("""
       select b.*,
       (rfp.*)::rackspace_files as rackspace_pdf,
       (rfd.*)::rackspace_files as rackspace_doc

       from bundles_expanded b
       left join rackspace_files as rfp
       on rfp.object_name = b.pdf_version
       left join rackspace_files as rfd
       on rfd.object_name = b.doc_version
       where b.binder_id = %(binder_id)s
       and b.folder_id = %(folder_id)s
       and b.bundle_status = %(bundle_status)s
       and now() <@ b.time_range
       order by b.inserted desc
        """), {'binder_id': binder_id,
               'folder_id':folder_id,
               'bundle_status':bundle_status
               })

    return cursor


def get_notes_to_file(pgconn, binder_id,
                      folder_id):
    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select nf.*, people.display_name
        from notes_to_file as nf
        join people on people.person_id = nf.owner_id
        where binder_id = (%s)
        and folder_id = (%s)

    """), [binder_id, folder_id])

    return cursor

def get_sticky_notes(pgconn, binder_id,
                      folder_id):
    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select sn.*, people.display_name
        from sticky_notes as sn
        join people on people.person_id = sn.owner_id
        where binder_id = (%s)
        and folder_id = (%s)

    """), [binder_id, folder_id])

    return cursor


def get_signatures(pgconn, file_id):
    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select *
        from uploaded_files
        where file_id= (%s)
    """), [file_id])

    return cursor


def parse_info_file(info_file_guts):

    """
    Example file::

        DESCRIPTION
        =========



        GUIDANCE
        =========



        INSTRUCTIONS
        =========



        FORMAT
        =========
        Has_File_Block=YES
        Has_Signature_Block=NO
        Default_PDF_File=Table_of_Contents.pdf
        Default_Word_File=NO
        Template_File=NO
        Template_Signature=NO
        Num_Allowed_Files=1
        Edit=NO
        1PDF_1Word=NO

    """

    sections = set(['DESCRIPTION', 'GUIDANCE', 'INSTRUCTIONS',
        'FORMAT'])

    current_section = None

    d = collections.defaultdict(list)

    for line in info_file_guts.split('\n'):

        # Skip blank lines and equal-sign lines
        if not line.strip() or not line.replace('=', '').strip():
            continue

        elif line.strip() in sections:
            current_section = line.strip()

        elif current_section:
            d[current_section].append(line)

    return d


def parse_format_section(format_section):

    d = dict()

    for line in format_section:

        k, v = line.strip().split('=')

        clean_v = v.strip().strip("'")

        if clean_v.lower() == 'no':
            d[k] = str(False)

        elif clean_v.lower() == 'yes':
            d[k] = str(True)

        elif clean_v.isdigit():

            d[k] = str(int(clean_v))

        elif clean_v.startswith('(') and clean_v.endswith(')'):

            d[k] = str(parse_file_tuples(clean_v))

        else:
            d[k] = clean_v

    return d


def parse_file_tuples(s):

    """
    >>> parse_file_tuples('(Contact_List.doc)')
    ['Contact_List.doc']

    """

    if s == '()':
        return []

    else:
        return s.lstrip('(').rstrip(')').split(',')


def maybe_upload_default_files(cw, folder_id, current_path):

    doc_files = glob.glob('{0}/*.doc'.format(current_path))
    pdf_files = glob.glob('{0}/*.pdf'.format(current_path))

    cloudconn = cw.make_new_cloudfile_connection()

    # This returns existing container if container already exists.
    df_container = cloudconn.create_container(
        'default_files')

    for path_to_file in doc_files + pdf_files:

        if not os.path.isfile(path_to_file):
            raise Exception('{0} is not real'.format(path_to_file))

        file_name = os.path.basename(path_to_file)
        object_name = '{0}-{1}'.format(folder_id, file_name)

        obj = df_container.create_object(object_name)
        obj.load_from_filename(path_to_file)
        log.info("Just uploaded {0} to cloud files".format(object_name))

        cursor = cw.get_pgconn().cursor()

        cursor.execute(textwrap.dedent("""
            insert into default_files
            (folder_id, filename, path_to_file)
            values
            (%s, %s, %s)"""),
            [folder_id, object_name, object_name])

        log.info("Just stored {0} in database.".format(object_name))


def find_file(path_to_file):

    pwd = os.path.dirname(path_to_file)

    matching_files = dict([(x.lower(), x) for x in os.listdir(pwd)
        if x.lower() == os.path.basename(path_to_file).lower()])

    if matching_files:

        return os.path.join(
            pwd,
            matching_files[os.path.basename(path_to_file).lower()])

    else:
        log.error('Could not find file {0}!'.format(path_to_file))

        # raise Exception('Could not find file {0}!'.format(path_to_file))


def upload_template_file(cw, folder_id, path_to_file):

    #cloudconn = cw.make_new_cloudfile_connection()
    pyrax = cw.get_pyrax_connection()

    # This returns existing container if container already exists.
    container = pyrax.cloudfiles.create_container('template_files')

    if not os.path.isfile(path_to_file):
        path_to_file = find_file(path_to_file)

    if not path_to_file:
        return

    file_name = os.path.basename(path_to_file)
    object_name = '{0}-{1}'.format(folder_id, file_name)

    uploaded_file = container.upload_file(path_to_file)
    #obj = container.create_object(object_name)
    #obj.load_from_filename(path_to_file)
    log.info("Just loaded {0} to cloud files".format(object_name))

    cursor = cw.get_pgconn().cursor()

    cursor.execute(textwrap.dedent("""
        insert into template_files
        (folder_id, filename, path_to_file)
        values
        (%s, %s, %s)"""),
        [folder_id, object_name, object_name])

    log.info("Just stored {0} in database.".format(object_name))


def get_default_files_for_folder_id(pgconn, folder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select (df.folder_id, df.filename, df.path_to_file, df.inserted,
        df.updated)::default_files as default_file

        from default_files df

        where folder_id = (%s)

        order by filename"""), [folder_id])

    return cursor


class DefaultFileCompositeFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return DefaultFile(**d)



class BoringFile(object):

    def make_temp_url(self):

        cw = configwrapper.ConfigWrapper.get_default()

        pyrax = cw.get_pyrax_connection()

        container = pyrax.cloudfiles.get_container(self.container_name)

        folder_id, object_name = self.filename.split('-', 1)

        file_object = container.get_object(object_name)

        time_available_in_seconds = cw.cloud_file_time_available

        return file_object.get_temp_url(time_available_in_seconds)

class DefaultFile(BoringFile):

    container_name = 'default_files'

    def __init__(self, folder_id, filename, path_to_file, inserted, updated):

        self.folder_id = folder_id
        self.filename = filename
        self.path_to_file = path_to_file
        self.inserted = inserted
        self.updated = updated

class TemplateFile(BoringFile):

    container_name = 'template_files'

    def __init__(self, folder_id, filename, path_to_file, inserted,
        updated):

        self.folder_id = folder_id
        self.filename = filename
        self.path_to_file = path_to_file
        self.inserted = inserted
        self.updated = updated

class UploadedFile(BoringFile):

    def __init__(self, file_id, owner_id, folder_id, binder_id,
        filename, path_to_pdf, path_to_word, uploader_comment,
        archived, inserted, updated):

        self.file_id = file_id
        self.owner_id = owner_id
        self.folder_id = folder_id
        self.binder_id = binder_id
        self.filename = filename
        self.path_to_pdf = path_to_pdf
        self.path_to_word = path_to_word
        self.uploader_comment = uploader_comment
        self.archived = archived
        self.inserted = inserted
        self.updated = updated

    def container_name(self):
        return self.binder_id


    def make_temp_url(self, fancy_file_id=None, use_pdf_path="PDF"):

        """

        Use pdf path otherwise use word

        """

        cw = configwrapper.ConfigWrapper.get_default()
        url = cw.cloud_base_url
        secret_key = cw.cloud_secret_key
        time_available_in_seconds = cw.cloud_file_time_available

        method = 'GET'
        base_url, unique_path = url.split('/v1/')

        path_to_file = self.path_to_pdf if use_pdf_path else self.path_to_word

        object_path = '/v1/{0}/{1}'.format(
            unique_path,
            path_to_file
            )

        extension = os.path.splitext(path_to_file)[1]

        output_filename = fancy_file_id +'-' + self.filename + extension \
                          if fancy_file_id else self.filename + extension

        expires = int(time.time() + int(time_available_in_seconds))

        hmac_body = '%s\n%s\n%s' % (method, expires, object_path)

        sig = hmac.new(secret_key, hmac_body, sha1).hexdigest()

        return '{0}{1}?temp_url_sig={2}&temp_url_expires={3}&filename={4}'.format(
            base_url,
            object_path,
            sig,
            expires,
            output_filename
            )


    @classmethod
    def from_file_id(cls, pgconn, file_uuid):

        cursor = pgconn.cursor()
        cursor.execute(textwrap.dedent("""
            select (uploaded_files.*)::uploaded_files
            from uploaded_files
            where file_id = (%s)
            """), [file_uuid])

        return cursor.fetchone()

    def look_up_display_names_for_esignatures(self, pgconn):

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select people.display_name,
            esignatures.extra_notes,
            esignatures.inserted
            from esignatures
            join people
            on esignatures.person_id = people.person_id
            where esignatures.file_id = %(file_id)s
            order by people.display_name
            """), {'file_id': self.file_id})

        return cursor


class UploadedSignature(BoringFile):

    def __init__(self, signature_id, file_id, owner_id,
                path_to_signature, signatories, inserted, updated):

        self.signature_id = signature_id
        self.file_id = file_id
        self.owner_id = owner_id
        self.path_to_signature = path_to_signature
        self.inserted = inserted
        self.updated = updated
        self.signatories = signatories

    def make_temp_url(self):

        cw = configwrapper.ConfigWrapper.get_default()
        url = cw.cloud_base_url
        secret_key = cw.cloud_secret_key
        time_available_in_seconds = cw.cloud_file_time_available

        method = 'GET'
        base_url, unique_path = url.split('/v1/')

        object_path = '/v1/{0}/{1}'.format(
            unique_path,
            self.path
            )

        expires = int(time.time() + int(time_available_in_seconds))

        hmac_body = '%s\n%s\n%s' % (method, expires, object_path)

        sig = hmac.new(secret_key, hmac_body, sha1).hexdigest()

        return '{0}{1}?temp_url_sig={2}&temp_url_expires={3}'.format(
            base_url,
            object_path,
            sig,
            expires)

class UploadedSignatureCompositeFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return UploadedSignature(**d)

class Signatory(object):

    def __init__(self, signatory_id,
                 name, binder_id,
                 inserted, updated):

        self.signatory_id = signatory_id
        self.name = name
        self.binder_id = binder_id
        self.inserted = inserted
        self.updated = updated



class SignatoryCompositeFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return Signatory(**d)

class Esignature(object):

    def __init__(self, file_id, person_id, extra_notes, inserted,
        updated):

        self.file_id = file_id
        self.person_id = person_id
        self.extra_notes = extra_notes
        self.inserted = inserted
        self.updated = updated

class EsignatureCompositeFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return Esignature(**d)

class SignatureWithSignatory():

    def __init__(self, file_id,
                 signature_id,
                 path_to_signature,
                 effective_date,
                 signatory_names):

        self.file_id = file_id
        self.signature_id = signature_id
        self.path_to_signature = path_to_signature
        self.effective_date = effective_date
        self.signatory_names = signatory_names

    def make_temp_url(self):

        cw = configwrapper.ConfigWrapper.get_default()
        url = cw.cloud_base_url
        secret_key = cw.cloud_secret_key
        time_available_in_seconds = cw.cloud_file_time_available

        method = 'GET'
        base_url, unique_path = url.split('/v1/')

        object_path = '/v1/{0}/{1}'.format(
            unique_path,
            self.path_to_signature
            )

        expires = int(time.time() + int(time_available_in_seconds))

        hmac_body = '%s\n%s\n%s' % (method, expires, object_path)

        sig = hmac.new(secret_key, hmac_body, sha1).hexdigest()

        return '{0}{1}?temp_url_sig={2}&temp_url_expires={3}'.format(
            base_url,
            object_path,
            sig,
            expires)

class SignaturesWithSignatoriesCompositeFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return SignatureWithSignatory(**d)

class BundleSignatureWithSignatoryNames():

    def __init__(self, signature_uuid,
                       bundle_id, owner_id,
                       object_name,
                       effective_date,
                       inserted,
                       updated,
                       sig_file,
                       signers):

        self.signature_uuid = signature_uuid
        self.bundle_id = bundle_id
        self.owner_id = owner_id
        self.object_name = object_name
        self.effective_date = effective_date
        self.inserted = inserted
        self.updated = updated
        self.sig_file = sig_file
        self.signers = signers




class BundleSignaturesWithSignatoryNamesFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return BundleSignatureWithSignatoryNames(**d)

class TemplateFileCompositeFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return TemplateFile(**d)

def get_template_files(pgconn, folder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select (folder_id, filename, path_to_file, inserted,
        updated)::template_files as template_file
        from template_files
        where folder_id = (%s)
    """), [folder_id])

    return cursor

def get_all_descendent_folders(pgconn, folder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        with recursive child_folders as (
            select * from folders where folder_id = (%(folder_id)s)
            union all
            select folders.* from folders join child_folders on
            folders.parent_folder_id = child_folders.folder_id
        )
        select *
        from child_folders
        """), {'folder_id': folder_id})

    return cursor


def get_most_recent_child_folder_upload(pgconn, binder_id, folder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
         with recursive child_folders as (
             select *
             from folders
             where folder_id = (%(folder_id)s)
             union all
             select folders.* from folders
             join child_folders
             on folders.parent_folder_id = child_folders.folder_id
         )

         select max(uf.inserted) as most_recent_upload

         from child_folders cf
         join uploaded_files uf
         on cf.folder_id = uf.folder_id
         and uf.binder_id = (%(binder_id)s)

         where cf.folder_id != (%(folder_id)s)
         """), {'binder_id': binder_id, 'folder_id': folder_id})

    return cursor.fetchone().most_recent_upload


def look_up_most_recent_signed_protocol_pdf(pgconn, binder_id, folder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select (uf.*)::uploaded_files as uploaded_file,

        nullif(
            array_agg((s.*)::signatures_with_signatories),
            array[NULL]::signatures_with_signatories[])
        as signatures,

        nullif(
            array_agg((es.*)::esignatures),
            array[NULL]::esignatures[])
        as esignatures

        from uploaded_files uf

        left join uploaded_signatures us
        on uf.file_id = us.file_id

        left join signatures_with_signatories as s
        on s.file_id = uf.file_id

        left join esignatures es
        on uf.file_id = es.file_id

        where uf.binder_id = (%(binder_id)s)
        and uf.folder_id = (%(folder_id)s)

        and (
            s.signature_id is not null
            or
            es.person_id is not null
        )

        group by uploaded_file, uf.inserted

        order by uf.inserted desc

        limit 1

        """), {
            'binder_id': binder_id,
            'folder_id': folder_id
        })

    return cursor

def look_up_most_recent_protocol_pdf(pgconn, binder_id, folder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""

        select (uf.*)::uploaded_files as uploaded_file,

        nullif(
            array_agg((s.*)::signatures_with_signatories),
            array[NULL]::signatures_with_signatories[])
        as signatures,

        nullif(
            array_agg((es.*)::esignatures),
            array[NULL]::esignatures[])
        as esignatures

        from uploaded_files uf

        left join signatures_with_signatories as s
        on s.file_id = uf.file_id

        left join esignatures es
        on uf.file_id = es.file_id

        where uf.binder_id = (%(binder_id)s)
        and uf.folder_id = (%(folder_id)s)

        group by uploaded_file, uf.inserted

        order by uf.inserted desc
        limit 1

        """), {
            'binder_id': binder_id,
            'folder_id': folder_id
        })

    return cursor


def make_training_guide_temp_url(cw, file_name):

        cw = configwrapper.ConfigWrapper.get_default()
        url = cw.cloud_base_url
        secret_key = cw.cloud_secret_key
        time_available_in_seconds = cw.cloud_file_time_available

        method = 'GET'
        base_url, unique_path = url.split('/v1/')

        object_path = '/v1/{0}/{1}/{2}'.format(
            unique_path,
            'training_files',
            file_name)

        expires = int(time.time() + int(time_available_in_seconds))

        hmac_body = '%s\n%s\n%s' % (method, expires, object_path)

        sig = hmac.new(secret_key, hmac_body, sha1).hexdigest()

        return '{0}{1}?temp_url_sig={2}&temp_url_expires={3}'.format(
            base_url,
            object_path,
            sig,
            expires)

def find_aggregate_folder_IDs(pgconn):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select folder_id
        from folders
        where folder_format ? 'agg'
        and folder_format->'agg' = 'True'
        """))

    return [row.folder_id for row in cursor.fetchall()]


def find_aggregate_folder_IDs_in_binder(pgconn, binder_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select folder_id, folder_format->'Title' as folder_pretty_title
        from folders
        where folder_format ? 'agg'
        and folder_format->'agg' = 'True'

        -- x <@ y means "are all elements in array x inside array y"?
        and array[folder_id] <@ (

            select fwc.descendents || array[fwc.folder_id]

            from folders_with_children fwc

            join binder_templates bt
            on fwc.folder_id = bt.root_folder_id

            join binders b
            on b.binder_template_id =
            bt.binder_template_id where binder_id = %(binder_id)s
        )"""), {'binder_id': binder_id})

    return cursor


class FolderFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))
        return Folder(**d)

class Folder(object):

    def __init__(self, folder_id, parent_folder_id, folder_title,
        description, guidance, instructions, raw_info, folder_format,
        inserted, updated):

        self.folder_id = folder_id
        self.parent_folder_id = parent_folder_id
        self.folder_title = folder_title
        self.description = description
        self.guidance = guidance
        self.instructions = instructions
        self.raw_info = raw_info
        self.folder_format = folder_format
        self.inserted = inserted
        self.updated = updated

    @classmethod
    def get_folders_I_monitor(cls, pgconn, binder_id, person_id):

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select (f.*)::folders as f

            from folders f

            join auditor_visibility av
            on av.folder_id = f.folder_id

            where av.binder_id = %(binder_id)s
            and av.person_id = %(person_id)s
            """), {'binder_id': binder_id, 'person_id': person_id})

        return cursor

    @property
    def is_front_page(self):

        return self.folder_format.get('FrontPage') == 'True'

    @property
    def is_a_log_folder(self):
        return 'Log' in self.folder_format
