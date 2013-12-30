# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import logging
import os
import textwrap
import hmac
import uuid
import subprocess
import mimetypes
import warnings

import psycopg2.extras

from time import time
from hashlib import sha1

log = logging.getLogger(__name__)

class RackspaceFile(object):

    def __init__(self, container, object_name, pretty_filename, binder_id,
                       folder_id, owner_id, file_purpose, file_type, inserted,
                       updated, pyrax_connection):

        self.container = container
        self.object_name = object_name
        self.pretty_filename = pretty_filename
        self.binder_id = binder_id
        self.folder_id = folder_id
        self.owner_id = owner_id
        self.file_purpose = file_purpose
        self.file_type = file_type
        self.inserted = inserted
        self.updated = updated
        self.pyrax_connection = pyrax_connection

        self.pgconn = None
        self.pyrax = None
        self.my_rackspace_object = None

    @classmethod
    def from_object_name(cls, pgconn, object_name):

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
             select(rackspace_files.*)::rackspace_files
             from rackspace_files
             where object_name = (%s)
             """), [object_name])

        rackspace_file = cursor.fetchone().rackspace_files

        rackspace_file.postgres_connection = pgconn

        return rackspace_file

    @classmethod
    def from_filepath( cls, pgconn,
                            pyrax_conn,
                            filepath,
                            binder_id,
                            folder_id,
                            owner_id,
                            pretty_filename=None,
                            file_type=None,
                            file_purpose=None):

        """
        You enter a file path like /home/matt/.vimrc, and this method
        will upload that file AND EVEN insert a row in the
        rackspace_files table for you!

        Finally, it will return a jazzy RackspaceFile instance just as
        if you queried the database.
        """

        object_name = uuid.uuid4()

        container = pyrax_conn.cloudfiles.get_container(str(binder_id))

        obj = container.upload_file(filepath,
                                    obj_name=str(object_name))

        if not pretty_filename:
            path, pretty_filename = os.path.split(filepath)

        if not file_type:
            guessed_file_type = mimetypes.guess_type(pretty_filename)[0]

        cursor = pgconn.cursor()
        cursor.execute(textwrap.dedent("""

            insert into rackspace_files
            (container, object_name, pretty_filename, binder_id,
            folder_id, owner_id, file_purpose, file_type)
            values
            (%(container)s, %(object_name)s, %(pretty_filename)s,
             %(binder_id)s, %(folder_id)s, %(owner_id)s,
             %(file_purpose)s,
             %(file_type)s)

            returning (rackspace_files.*)::rackspace_files

            """), {'container': binder_id,
                   'object_name': object_name,
                   'pretty_filename': pretty_filename,
                   'binder_id': binder_id,
                   'folder_id': folder_id,
                   'owner_id': owner_id,
                   'file_type': file_type or guessed_file_type,
                   'file_purpose': file_purpose or 'user-uploaded file'})

        return cursor.fetchone().rackspace_files

    @property
    def postgres_connection(self):
        warnings.warn('Are you sure you need this as a property?')
        return self.pgconn

    @postgres_connection.setter
    def postgres_connection(self, value):
        self.pgconn= value

    @property
    def is_pdf(self):
        return self.file_type == 'application/pdf'

    def is_doc(self):

        is_doc = (self.file_type == 'application/msword' or
                  self.file_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')

        if not is_doc:
            return 'doc' in self.extension
        else:
            return is_doc

    def is_xls(self):

        is_pdf = (self.file_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' or
                  self.file_type == 'application/vnd.ms-excel')

        if not is_pdf:
            return 'xls' in self.extension
        else:
            return is_pdf

    @property
    def pretty_filename_no_extension(self):

        filename, extension = os.path.splitext(self.pretty_filename)
        return filename

    @property
    def extension(self):
        if self.file_type == 'application/pdf':
            return 'pdf'
        elif self.file_type == 'application/msword':
            return 'doc'
        elif self.file_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            return 'docx'


        #if none of these, try this:
        filename, extension = os.path.splitext(self.pretty_filename)
        return extension.strip('.')

    def get_my_rackspace_object(self, pyrax):

        """
        Use this to get something that you can use to do stuff like
        get_temp_url...
        """

        if not self.my_rackspace_object:

            log.info('Getting the object {0} from rackspace...'.format(
                self.object_name))

            container = pyrax.cloudfiles.get_container(self.container)

            self.my_rackspace_object = container.get_object(
                str(self.object_name))

        return self.my_rackspace_object

    # aliases are awesome
    get_rackspace_object = get_my_rackspace_object

    def make_temp_url(self, pretty_filename=None):

        """

        Use pdf path otherwise use word

        """

        temp_url = self.pyrax_connection.cloudfiles.get_temp_url(
                                                 self.container,
                                                 str(self.object_name),
                                                 60*60)

        if pretty_filename:
            return temp_url+'&filename='+pretty_filename+'.'+self.extension

        else:
            return temp_url+'&filename='+str(self.object_name)+'.'+self.extension

    @staticmethod
    def convert_a_rackspace_file_to_pdf_and_insert(rackspace_file,
                                                   binder_id,
                                                   folder_id,
                                                   owner_id,
                                                   pyrax_conn,
                                                   pgconn):


        pyrax_object = rackspace_file.get_my_rackspace_object(pyrax_conn)

        pyrax_object.download('/tmp', structure=False)

        #filename is object name
        filepath = os.path.join('/tmp',
                             str(rackspace_file.object_name))

        log.debug('Start conversion to PDF')

        #This isn't the best solution...
        #check output will blow up
        #Unoconv likes to throw a floating point exception ever
        #once in a while for no clear reason.. and still converts the file
        # -- while we investigate further, squelch the exception --
        try:
            subprocess.check_output(['unoconv', filepath])

        except subprocess.CalledProcessError as e:
            log.error(e)


        log.debug('Conversion to PDF Complete')

        pdf_filepath = filepath + '.pdf'

        return RackspaceFile.from_filepath(
                            pgconn,
                            pyrax_conn,
                            pdf_filepath,
                            binder_id,
                            folder_id,
                            owner_id)


    def __repr__(self):

        return '<{0}.{1} ({2}/{3}/{4}/{5})>'.format(
                self.__class__.__module__,
                self.__class__.__name__,
                self.binder_id,
                self.folder_id,
                self.pretty_filename,
                self.object_name)

    def mark_for_destruction(self, pgconn):

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            update rackspace_files
            set file_purpose = 'destroy me'
            where object_name = (%s)
            """), [self.object_name])

        log.info("Updated rackspace file {0} file_purpose to "
            "'destroy me'".format(self))

        return self


class RackspaceFileCompositeFactory(psycopg2.extras.CompositeCaster):

    def make(self, values):
        d = dict(zip(self.attnames, values))

        #if you can think of a better way to do
        from horsemeat import configwrapper
        cw = configwrapper.ConfigWrapper.get_default()
        cw.get_pyrax_connection()
        d['pyrax_connection'] = cw.get_pyrax_connection()


        return RackspaceFile(**d)


def store_file(pgconn, cloudconn, person_id,
               binder_id, folder_id,
               file_storage_pdf, filename,
               uploader_comment=None,
               file_storage_word = None):

    """
    Example usage::

        files = dict(req.files)

        uploadedfile.store_file(
            self.pgconn,
            self.cw.make_new_cloudfile_connection(),
            req.user.person_id,
            binder_id,
            folder_id,
            files.get('pdf')[0],
            uploader_comment,
            files.get('word')[0] if files.get('word') else None)

    """

    destination_dir = '/tmp'

    if not os.path.exists(destination_dir):
        os.mkdir(destination_dir)

    unique_id = uuid.uuid4()
    #figure out my unique id
    #unique_id = create_unique_file_id(pgconn, binder_id, folder_id)

    # Container creation based on binder number. Returns container
    # if one already exists
    cont = cloudconn.create_container(str(binder_id))

    #we must have pdf, so do that first
    pdf_file = save_file_to_local_filesystem(destination_dir,
                                             file_storage_pdf)

    extension = os.path.splitext(file_storage_pdf.filename)[1]

    pdf_cloudpath = save_to_cloudfiles(cont, pdf_file,
                                       filename,
                                       extension,
                                       unique_id)

    word_cloudpath = None

    if (file_storage_word and file_storage_word.filename):
        word_file = save_file_to_local_filesystem(destination_dir,
                                                  file_storage_word)
        extension = os.path.splitext(file_storage_word.filename)[1]
        word_cloudpath = save_to_cloudfiles(cont,
                                            word_file,
                                            filename,
                                            extension,
                                            unique_id)


    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        insert into uploaded_files
        (file_id, owner_id, binder_id,
         folder_id, filename, path_to_pdf,
         path_to_word, uploader_comment)
        values
        (%s, %s, %s, %s, %s, %s, %s, %s)
        """),
        [unique_id, person_id, binder_id,
         folder_id, filename,
         pdf_cloudpath, word_cloudpath, uploader_comment])


def store_signature(pgconn, cloudconn, person_id,
               binder_id, file_id,
               effective_dt,
               file_storage_signature,
               signatories):

    destination_dir = '/tmp'

    if not os.path.exists(destination_dir):
        os.mkdir(destination_dir)

    unique_sig_uuid = uuid.uuid4()
    # Container creation based on binder number. Returns container
    # if one already exists
    # preface with signature
    cont = cloudconn.create_container(str(binder_id) + "-signatures")

    #we must have pdf, so do that first
    sig_file = save_file_to_local_filesystem(destination_dir,
                                             file_storage_signature)


    filename, extension = os.path.splitext(sig_file.filename)
    sig_cloudpath = save_to_cloudfiles(cont, sig_file,
                                       file_storage_signature,
                                       filename,
                                       extension,
                                       unique_sig_uuid)

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        insert into uploaded_signatures
        (signature_id, file_id, owner_id,
          effective_date,
          path_to_signature)
        values
        (%s, %s, %s, %s, %s)
        """),
        [unique_sig_uuid, file_id, person_id,
         effective_dt,
         sig_cloudpath])

    # Now add each signatory if it's not.
    # Otherwise connect signatories

    for sig in signatories:
        cursor.execute(textwrap.dedent("""

            insert into signatories
            (name, binder_id)
            values
            (%s, %s)
            returning signatory_id
            """),
            [ sig, binder_id ])

        signatory_id = cursor.fetchone().signatory_id

        # Now tie signatory and signature together
        cursor.execute(textwrap.dedent("""

            insert into uploaded_signature_signatory_link
            (signatory_id, signature_id)
            values
            (%s, %s)
            """),
            [ signatory_id, unique_sig_uuid ])


def store_bundle_signature(cw, person_id,
               bundle_id,
               object_name,
               effective_dt,
               signatories):

    cursor = cw.get_pgconn().cursor()

    cursor.execute(textwrap.dedent("""
        insert into uploaded_bundle_signatures
        (bundle_id, owner_id,
         object_name, effective_date
         )
        values
        (%s, %s, %s, %s)
        returning
        signature_uuid
        """),
        [bundle_id, person_id,
         object_name,
         effective_dt])

    signature_uuid = cursor.fetchone().signature_uuid

    # Now add each signatory if it's not.
    # Otherwise connect signatories

    for sig in signatories:
        cursor.execute(textwrap.dedent("""

            insert into bundle_signatories
            (name, signature_uuid)
            values
            (%s, %s)
            """),
            [ sig, signature_uuid ])






def save_file_to_local_filesystem(destination_dir, file_storage):

    """

    Give us a file storage object and we'll give you a file name back

    """

    destination_filename = os.path.join(
        destination_dir, file_storage.filename)

    f = open(destination_filename, 'w')

    f.write(file_storage.read())
    f.close()

    return destination_filename


def save_to_cloudfiles(container,
                       local_file,
                       filename,
                       extension,
                       unique_id):

    longform_filename = create_longform_filename(unique_id,
                                                 filename,
                                                 extension)

    # Save the file in Cloud files
    container.create_object(longform_filename). \
               load_from_filename(local_file)

    #let's make a new name using a uuid
    cloud_path = os.path.join(container.name, longform_filename)

    return cloud_path




def create_unique_file_id(pgconn, binder_id, folder_id):

    cursor = pgconn.cursor()

    sequence_string = 'filesequence_{0}_{1}'.format(binder_id, folder_id)

    query = "select nextval('{0}')".format(sequence_string)

    cursor.execute(query)


    #No idea why, but the query returns with an 'L'
    #We should strip it off...
    file_id = cursor.fetchone().nextval

    return "{0}-{1}-{2}".format(binder_id, folder_id, str(file_id))

    #look up next number in sequence for given
    #binder and folder id

"""
If we ever want to make this more complicated, we can,
but for now just concatenate the uuid and the filename.

This should be unique enough

extension should be in form '.ext'

"""

def create_longform_filename(unique_uuid, filename, extension):

    return str(unique_uuid) + "-" + filename  + extension


"""

Cloud Files uses temporary urls to provide access
to files that are not publicly available. Using
a secret key set for our account, we can
generate a unique hash. Also, the time limit
the url will be available is settable in seconds.

"""
def create_temp_url(url, path_to_file,
                    secret_key,
                    time_available_in_seconds):

    method = 'GET'
    base_url, unique_path = url.split('/v1/')
    object_path = '/v1/' + unique_path + '/' + path_to_file
    seconds = int(time_available_in_seconds)
    expires = int(time() + seconds)
    hmac_body = '%s\n%s\n%s' % (method, expires, object_path)
    sig = hmac.new(secret_key, hmac_body, sha1).hexdigest()

    return '%s%s?temp_url_sig=%s&temp_url_expires=%s' % \
        (base_url, object_path, sig, expires)


