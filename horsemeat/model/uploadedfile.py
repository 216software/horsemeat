# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import logging
import os
import textwrap
import hmac
import uuid

from time import time
from hashlib import sha1

from horsemeat.model import rackspacefile

log = logging.getLogger(__name__)

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


def store_bundle_signature_with_file(pgconn, pyrax_conn, person_id,
               binder_id, folder_id, bundle_id,
               effective_dt,
               file_storage_signature,
               signatories):


    # Container creation based on binder number. Returns container
    # if one already exists
    # preface with signature

    #we must have pdf, so do that first
    rf = rackspacefile.RackspaceFile.from_filepath(pgconn, pyrax_conn,
                                     file_storage_signature,
                                     binder_id,
                                     folder_id,
                                     person_id,
                                     'signature.pdf')

    cursor = pgconn.cursor()
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
         rf.object_name,
         effective_dt])

    # Now add each signatory if it's not.
    # Otherwise connect signatories

    signature_uuid =cursor.fetchone().signature_uuid

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

