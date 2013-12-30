# vim: set expandtab ts=4 sw=4 filetype=python:

import contextlib
import logging
import logging.config
import smtplib
import sys
import traceback
import uuid
import warnings

import clepy
import cloudfiles
import jinja2
import pkg_resources
import psycopg2, psycopg2.extras
import pyrax
import yaml

log = logging.getLogger(__name__)

class ConfigWrapper(object):

    """
    Use this class to interact with our configuration files.  Add properties
    and methods so that app code doesn't have to think too much about the
    way the data is stored in the config files, and so that we can
    reorganize stuff.
    """

    # Later, you can set up a particular instance as the default instance.
    default_instance = None

    # Keep a reference of the instances made from each yaml file.
    instances = dict()

    # Just an alias.
    already_instantiated = instances

    # Allow all instances to share a connection to the postgresql database.
    postgresql_connection = None

    # Allow all instances to share a jinja2 environment.
    jinja2_environment = None

    # Allow all instances to share a connection to the cloud files
    cloudfile_connection = None

    # Allow instances to share an SMTP connection.
    smtp_connection = None

    pyrax_connection = None

    def __init__(self, config_dictionary):
        self.config_dictionary = config_dictionary

    @classmethod
    def from_yaml_file_name(cls, filename, force_reload=False):

        """
        Loads one of the yaml files in the config_files folder.

        Calling this repeatedly for the same file WILL NOT reload the
        file unless you set force_reload to True.

        If you are modifying the ConfigWrapper instance, then you're
        doing something wrong.

        >>> ConfigWrapper.from_yaml_file_name('matt.yaml') # doctest: +SKIP
        <ConfigWrapper>

        """
        if not filename:
            raise ValueError("Sorry, I need a filename!")

        if filename in cls.instances and not force_reload:
            return cls.instances[filename]

        else:

            stream = pkg_resources.resource_stream(
                'horsemeat.configs.yaml_files',
                filename)

            self = cls(yaml.load(stream))

            cls.instances[filename] = self

            return self

    def get_postgresql_connection(self, register_composite_types=True):

        if not self.postgresql_connection:

            self.make_database_connection(
                register_composite_types=register_composite_types)

        return self.postgresql_connection

    # Short aliases are fun too.
    get_pgconn = get_postgresql_connection


    def get_cloudfile_connection(self):

        1/0

        "DO NOT USE THIS!  ALWAYS CREATE A NEW CONNECTION!"

        if not self.cloudfile_connection:
            cloudconn = self.make_new_cloudfile_connection()
            self.__class__.cloudfile_connection = cloudconn

        return self.cloudfile_connection

    @property
    def cloudfile_connection_data(self):
        return dict(
           username=self.config_dictionary['cloudfiles']['username'],
           api_key = self.config_dictionary['cloudfiles']['api-key'])

    def make_new_cloudfile_connection(self):

        cloudconn = cloudfiles.Connection(**self.cloudfile_connection_data)

        log.info("Just made cloudfile connection {0}.".format(cloudconn))

        return cloudconn


    @contextlib.contextmanager
    def get_autocommitting_postgresql_connection(self):

        """
        Use this thing like this::

        >>> with cw.get_autocommitting_postgresql_connection \
        ... as pgconn: # doctest: +SKIP
        ...     cursor = pgconn.cursor()
        ...     cursor.execute("update ...")

        ]and the transaction will be committed when you leave the with
        block.

        """

        try:
            yield self.get_postgresql_connection()

        finally:
            log.info("Committing postgresql connection...")
            self.postgresql_connection.commit()

    @property
    def postgresql_connection_data(self):

        return dict(
            port=self.config_dictionary['postgresql']['port'],
            database=self.config_dictionary['postgresql']['database'],
            host=self.config_dictionary['postgresql']['host'],
            user=self.config_dictionary['postgresql']['user'],
            password=self.config_dictionary['postgresql']['password'])

    @property
    def database_host(self):
        return self.config_dictionary['postgresql']['host']

    @property
    def database_port(self):
        return self.config_dictionary['postgresql']['port']

    @property
    def database_database(self):
        return self.config_dictionary['postgresql']['database']

    # Since database_database sounds stupid, I'm setting up an alias
    # "database_name".
    database_name = database_database

    @property
    def database_user(self):
        return self.config_dictionary['postgresql']['user']

    def make_database_connection(self, register_composite_types=True):

        pgconn = psycopg2.connect(
            connection_factory=psycopg2.extras.NamedTupleConnection,
            **self.postgresql_connection_data)

        log.info("Just made postgresql connection {0}.".format(pgconn))

        # Keep a reference to this connection on the class, so that
        # other instances can just recycle this connection.
        self.__class__.postgresql_connection = pgconn

        psycopg2.extras.register_uuid()
        psycopg2.extras.register_hstore(pgconn, globally=True)

        psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
        psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)

        if register_composite_types:
            self.register_composite_types(pgconn)

        return pgconn

    # Make an alias because Matt can't remember stuff good.
    create_postgresql_connection = make_database_connection

    def register_composite_types(self, pgconn):

        from horsemeat.model.folder import \
        UploadedFileCompositeFactory, UploadedSignatureCompositeFactory, \
        SignaturesWithSignatoriesCompositeFactory, \
        BundleSignaturesWithSignatoryNamesFactory, \
        TemplateFileCompositeFactory, \
        DefaultFileCompositeFactory, \
        EsignatureCompositeFactory, \
        FolderFactory

        psycopg2.extras.register_composite('template_files', pgconn,
            factory=TemplateFileCompositeFactory)

        psycopg2.extras.register_composite('uploaded_files', pgconn,
            factory=UploadedFileCompositeFactory)

        psycopg2.extras.register_composite('signatures_with_signatories',
            pgconn, factory=SignaturesWithSignatoriesCompositeFactory)

        psycopg2.extras.register_composite('default_files', pgconn,
            factory=DefaultFileCompositeFactory)

        psycopg2.extras.register_composite('esignatures', pgconn,
            factory=EsignatureCompositeFactory)

        psycopg2.extras.register_composite(
            'folders',
            pgconn,
            factory=FolderFactory)

        from horsemeat.model.rackspacefile import \
        RackspaceFileCompositeFactory

        psycopg2.extras.register_composite('rackspace_files', pgconn,
            factory=RackspaceFileCompositeFactory)

        from horsemeat.model.user import PersonFactory

        psycopg2.extras.register_composite('people', pgconn,
            factory=PersonFactory)

        from horsemeat.model.bundle import \
        BundleFactory, \
        BundleEsignatureFactory

        psycopg2.extras.register_composite('bundles', pgconn,
            factory=BundleFactory)

        psycopg2.extras.register_composite('bundle_esignatures', pgconn,
            factory=BundleEsignatureFactory)

        psycopg2.extras.register_composite(
            'bundle_signatures_with_signatory_names',
            pgconn,
            factory=BundleSignaturesWithSignatoryNamesFactory)

        from horsemeat.model.binders import \
        BinderFactory, BinderTemplateFactory

        psycopg2.extras.register_composite('binders', pgconn,
          factory=BinderFactory)

        psycopg2.extras.register_composite('binder_templates', pgconn,
          factory=BinderTemplateFactory)

        from horsemeat.queries.clients import ClientCompositeFactory

        psycopg2.extras.register_composite('clients', pgconn,
          factory=ClientCompositeFactory)

        from horsemeat.model.session import SessionFactory

        psycopg2.extras.register_composite('horsemeat_sessions', pgconn,
          factory=SessionFactory)

        from horsemeat.model.visibility import VisibilitySettingsFactory

        psycopg2.extras.register_composite('visibility_settings', pgconn,
          factory=VisibilitySettingsFactory)


        log.info('Just registered composite types in psycopg2')

        return pgconn


    def configure_logging(self, process_type='default'):

        if 'logging' not in self.config_dictionary:
            raise MissingConfig("You need to set a logging key!")

        elif process_type not in self.config_dictionary['logging']:

            raise MissingConfig("I don't know how to configure "
                "logging for {0} processes!  You need to set a key for "
                "{0} processes in the logging section.".format(
                    process_type))

        else:

            x = self.config_dictionary['logging'][process_type]

            if isinstance(x, str):

                warnings.warn("Stop it! Define logging configuration "
                    "the same YAML file!")

                logging.config.fileConfig(
                    pkg_resources.resource_filename(
                        'horsemeat.configs.logging_configs',
                        x))

            elif isinstance(x, dict):
                logging.config.dictConfig(x)

            else:
                raise Exception("can not deal with x: {0}.".format(x))

        log.info('Just configured logging...')

    def set_as_default(self):

        self.__class__.default_instance = self
        return self

    @classmethod
    def get_default(cls):

        if cls.default_instance:
            return cls.default_instance

        else:
            raise ValueError("Sorry!  No default configwrapper "
                "instance has been set!")

    @property
    def app_secret(self):

        try:
            return self.config_dictionary['app']['secret']

        except KeyError:
            raise MissingConfig("Didn't find an app secret!")

    @property
    def cloud_base_url(self):

        try:
            return self.config_dictionary['cloudfiles']['base-url']

        except KeyError:
            raise MissingConfig("Didn't find a cloudfiles base url!")

    @property
    def cloud_secret_key(self):

        try:
            return self.config_dictionary['cloudfiles']['temp-url-key']

        except KeyError:
            raise MissingConfig("Didn't find a cloudfiles secret key!")

    @property
    def cloud_file_time_available(self):

        try:
            return int(self.config_dictionary['cloudfiles']['time-available'])

        except KeyError:
            raise MissingConfig("Didn't find cloudfiles time available!")

    def make_jinja2_environment(self):

        j = jinja2.Environment(
            autoescape=True,

            # Tell jinja2 to blow up when we reference an undefined var
            # in a template.  Otherwise, it will get printed as an empty
            # string.
            undefined=jinja2.StrictUndefined,

            loader=jinja2.PrefixLoader({

                'framework_templates':jinja2.PackageLoader(
                    'horsemeat.webapp.framework',
                    'framework_templates'),

            }),

            extensions=['jinja2.ext.loopcontrols'],
        )

        log.info("Just built a jinja2 environment")

        self.__class__.jinja2_environment = j

        # Add a bunch of stuff to the template namespace.
        j.globals['getattr'] = getattr
        j.globals['hasattr'] = hasattr
        j.globals['clepy'] = clepy
        j.globals['dir'] = dir
        j.globals['zip'] = zip
        j.globals['uuid'] = uuid
        j.globals['mathset'] = set
        j.globals['sorted'] = sorted

        # Give jinja a reference to the configwrapper.
        j.globals['cw'] = self

        return j

    def get_jinja2_environment(self):

        if not self.jinja2_environment:
            self.make_jinja2_environment()

        return self.jinja2_environment

    @property
    def scheme(self):
        return self.config_dictionary['app']['scheme']

    @property
    def host(self):
        return self.config_dictionary['app']['host']

    @property
    def web_host(self):
        return '{scheme}://{host}'.format(
            scheme=self.scheme,
            host=self.host)

    def make_location_from_path(self, path):

        """
        >>> cw = ConfigWrapper({'app': {'scheme': 'http', 'host': 'example.com'}})
        >>> cw.make_location_from_path('/login')
        'http://example.com/login'

        """

        return '{0}://{1}{2}'.format(
            self.scheme,
            self.host,
            path)

    @property
    def smtp_host(self):
        return self.config_dictionary['smtp']['host']

    def make_smtp_connection(self):

        """
        I'm not trying any fancy recycled connection stuff here.  It
        seems like the localhost SMTP server closes old connections
        automatically.
        """

        return smtplib.SMTP(self.smtp_host)

    @property
    def launch_debugger_on_error(self):

        """
        This defaults to False if the config file has no entry.
        """

        if 'launch_debugger_on_error' \
        not in self.config_dictionary['app']:
            return False

        else:
            return self.config_dictionary['app']['launch_debugger_on_error']

    def do_pyrax_stuff(self):

        """
        Probably needs a better name, like "authenticate with pyrax".
        """

        log.info("Setting up a new pyrax object...")

        if self.pyrax_connection:
            warnings.warn("NO! Use self.get_pyrax_connection instead!")

        pyrax.set_setting('identity_type',  'rackspace')

        pyrax.set_credentials(
            self.config_dictionary['cloudfiles']['username'],
            self.config_dictionary['cloudfiles']['api-key'],
            region="ORD")

        log.info("Set settings and credentials on pyrax")

        return pyrax

    def get_pyrax_connection(self):

        """
        Just like the other get_* methods, this returns an
        already-created instance if it exists.
        """

        if not self.pyrax_connection:
            self.pyrax_connection = self.do_pyrax_stuff()

        return self.pyrax_connection

    @property
    def protocol_folder_id(self):

        try:
            return self.config_dictionary\
            ['special_folders']['protocol_folder_id']

        except KeyError:
            raise MissingConfig(
                "Sorry, couldn't find a protocol folder ID key!")

    @property
    def table_of_contents_folder_id(self):

        try:
            return self.config_dictionary\
            ['special_folders']['table_of_contents_folder_id']

        except KeyError:
            raise MissingConfig(
                "Sorry, couldn't find a protocol folder ID key!")

    @property
    def current_irb_approved_submission_folder_id(self):
        try:
            return self.config_dictionary\
            ['special_folders']['current_irb_approved_submission']

        except KeyError:
            raise MissingConfig(
                "Sorry, couldn't find a key for the current "
                "IRB-approved submission folder ID!")

    @property
    def annual_irb_approved_submission_folder_id(self):

        try:
            return self.config_dictionary\
            ['special_folders']['annual_irb_approved_submission']

        except KeyError:
            raise MissingConfig(
                "Sorry, couldn't find a key for the "
                "Annual IRB-approved submission folder ID!")

    @property
    def oversight_folder_id(self):

        try:
            return self.config_dictionary\
            ['special_folders']['oversight']

        except KeyError:
            raise MissingConfig(
                "Sorry, couldn't find a key for the "
                "oversight folder ID!")


    def verify_config_file(self):

        """
        This makes sure a bunch of fields are defined in the config
        file.

        It doesn't verify the data is correct.  It just verifies
        it exists.

        Returns self if file is A-OK, otherwise, raises a MissingConfig
        exception on the first missing value.
        """

        # We could make the "important_properties" list dynamically.
        # We could write our own decorator named "important_property"
        # that we used instead of the regular property decorator.
        # "important_property" would do the same thing as the regular
        # property decorator, but it would also append the particular
        # property to a class-level (not instance level!) array
        # attribute.

        important_properties = [
            'postgresql_connection_data',
            'cloudfile_connection_data',
            'smtp_host',
            'web_host',
            'table_of_contents_folder_id',
            'protocol_folder_id',
            'current_irb_approved_submission_folder_id',
            'annual_irb_approved_submission_folder_id',
            'oversight_folder_id',
        ]

        log.debug('Verifying config file contents:')

        for propname in important_properties:

            log.debug('{0}: {1}'.format(
                propname,
                getattr(self, propname)))

        # This else clause fires in the event that the for-loop
        # completed.  Weird, right?  The only way to not go into the else
        # clause below is to use a break statement.

        else:
            log.info("Config file contains all required data")
            return self

    def connect_everything(self):

        """
        Make connections to all the external services we need.
        """

        self.get_postgresql_connection()
        self.get_pyrax_connection()

    @property
    def dev_mode(self):

        return 'dev' == self.config_dictionary['app'].get(
            'mode',
            'production')

    @property
    def production_mode(self):
        return not self.dev_mode


class MissingConfig(KeyError):

    """
    You need to add some more stuff to your config file!
    """

def log_uncaught_exceptions(ex_cls, ex, tb):
    log.critical(''.join(traceback.format_tb(tb)))
    log.critical('{0}: {1}'.format(ex_cls, ex))

    if hasattr(ex, 'errors') and ex.errors:
        log.critical(ex.errors)
