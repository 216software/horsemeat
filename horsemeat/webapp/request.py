# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import cgi
import collections
import Cookie
import hmac
import inspect
import json
import logging
import re
import textwrap
import urllib
import urlparse
import warnings
import wsgiref.util

from werkzeug.wrappers import Request as WerkzeugRequest

log = logging.getLogger(__name__)

class Request(collections.MutableMapping):

    """
    Wraps up the environ dictionary in an object with lots of cute
    properties.

    But if you want to pretend the request IS the environ dictionary,
    you can.
    """

    def __init__(self, pgconn, config_wrapper, environ):
        self.pgconn = pgconn
        self.config_wrapper = config_wrapper
        self.environ = environ

        # This is the maximum amount of data to read into memory.
        # The number below is about 10 megabytes.
        self.maximum_buffer_size = 10 * 1000 * 1000

    @property
    def HTTP_COOKIE(self):
        return self.get('HTTP_COOKIE')

    @property
    def PATH_INFO(self):
        return self.get('PATH_INFO')

    @property
    def REQUEST_METHOD(self):
        return self.get('REQUEST_METHOD')

    @property
    def QUERY_STRING(self):
        return self.get('QUERY_STRING')

    @property
    def is_GET(self):
        return self.get('REQUEST_METHOD') == 'GET'

    @property
    def is_POST(self):
        return self.get('REQUEST_METHOD') == 'POST'

    @property
    def parsed_QS(self):

        # Notice that this is a unicode docstring!
        u"""
        >>> req = Request(None, None, {'QUERY_STRING':'flavor=Jalapeño'})

        >>> req.parsed_QS['flavor'][0] == u'Jalape\xf1o' # doctest: +SKIP
        True

        >>> req.parsed_QS['flavor'][0] == u'Jalapeño' # doctest: +SKIP
        True

        >>> print req.parsed_QS['flavor'][0] # doctest: +SKIP
        Jalapeño

        """

        if 'parsed_QS' in self:
            return self['parsed_QS']

        if self.QUERY_STRING:
            parsed_qs = urlparse.parse_qs(
                urllib.unquote(self.QUERY_STRING).decode(self.charset),
                keep_blank_values=1)

        else:
            parsed_qs = {}

        self['parsed_QS'] = parsed_qs
        return parsed_qs

    @property
    def parsed_cookie(self):

        if self.HTTP_COOKIE:
            c = Cookie.SimpleCookie()
            c.load(self.HTTP_COOKIE)
            return c

    @property
    def body(self):

        """
        Don't use this if you suspect you might get a POST that's so big
        that you can't load it all into memory.

        """

        if not self.get('CONTENT_LENGTH'):
            return

        if 'request.body' in self:
            return self['request.body']

        else:

            b = self.read_request_body()

            self['request.body'] = b

            return self['request.body']


    def read_request_body(self):

        """
        If the content length is small enough, just read everything into
        memory.

        Otherwise, raise an exception.  One day, I'll figure out how to
        write stuff out to tempfiles.
        """

        if self.parsed_content_length > self.maximum_buffer_size:
            raise BiggerThanMemoryBuffer(
                "I can't load {0} bytesinto memory!".format(
                    self.parsed_content_length))

        elif 'wsgi.input' in self and self.parsed_content_length:

            return self['wsgi.input'].read(int(self['CONTENT_LENGTH']))


    @property
    def parsed_content_length(self):

        if 'parsed_content_length' in self:
            return self['parsed_content_length']

        else:
            x = self.get('CONTENT_LENGTH')
            if x:
                parsed_content_length = int(x)
                self['parsed_content_length'] = parsed_content_length
                return parsed_content_length

    @property
    def wz_req(self):

        if 'werkzeug_request' not in self:
            self['werkzeug_request'] = WerkzeugRequest(self)

        return self['werkzeug_request']

    @property
    def parsed_multi(self):

        return self.wz_req.form

    @property
    def files(self):

        # TODO: reconsider this -- it just hides the obvious truth.

        if 'request.files' not in self:
            self['request.files'] = self.wz_req.files

        return self['request.files']

    @property
    def signed_in_user_display_name(self):
        if self.user:
            return self.user.display_name

    @property
    def parsed_body(self):

        # Notice this is a unicode string!
        u"""

        Return a dictionary of keys and values by parsing the the body.

        This stuff is just setup:

        >>> import io
        >>> bogus_wsgi_input = io.BytesIO()
        >>> bogus_wsgi_input.write('flavor=Jalapeño&novalue=') # doctest: +SKIP
        25L
        >>> bogus_wsgi_input.seek(0) == 0
        True

        Here's the doctest:

        >>> req = Request(None, None, {'REQUEST_METHOD':'POST',
        ...     'wsgi.input': bogus_wsgi_input,
        ...     'CONTENT_LENGTH': len('flavor=Jalapeño&novalue=')})

        >>> req.parsed_body['flavor'][0] == u'Jalape\xf1o' # doctest: +SKIP
        True

        >>> print req.parsed_body['flavor'][0] # doctest: +SKIP
        Jalapeño

        >>> 'novalue' in req.parsed_body # doctest: +SKIP
        True

        """

        if 'horsemeat.parsed_body' in self:
            return self['horsemeat.parsed_body']

        if self.body:

            try:
                self['horsemeat.parsed_body'] = urlparse.parse_qs(
                    urllib.unquote(self.body).decode(self.charset),
                    keep_blank_values=1)

            except UnicodeDecodeError as e:

                log.exception(e)
                log.error("Cannot decode parsed body. Probably dealing with a file upload")
                self['horsemeat.parsed_body'] = {}

        else:
            self['horsemeat.parsed_body'] = {}

        return self['horsemeat.parsed_body']


    @property
    def redirect_cookie(self):

        """
        When the browser sends a header like this::

            Cookie: redirect-to=http://example.com/my-account

        this property will return::

            http://example.com/my-account

        """

        # TODO: move this stuff into the session table from the cookie.

        if 'horsemeat.redirect_cookie' in self:
            return self['horsemeat.redirect_cookie']

        if self.parsed_cookie and 'redirect-to' in self.parsed_cookie:
            loc = self.parsed_cookie['redirect-to'].value
            self['horsemeat.redirect_cookie'] = loc
            return loc


    # These magic methods allow the Request object to act like a
    # dictionary.
    def __getitem__(self, k):
        return self.environ[k]

    def __delitem__(self, k):
        return self.environ.__delitem__(k)

    def __setitem__(self, k, v):
        self.environ[k] = v

    def __iter__(self):
        return iter(self.environ)

    def __len__(self):
        return len(self.environ)

    @property
    def HTTP_REFERER(self):
        return self.get('HTTP_REFERER')

    @property
    def news_message_cookie(self):

        """
        Return None if no news-message cookie exists.

        If the news-message cookie does exist, then unquote it and
        return it.
        """

        if 'horsemeat.news_message_cookie' in self:
            x = self['horsemeat.news_message_cookie']
            return x

        if self.parsed_cookie and 'news-message' in self.parsed_cookie:
            quoted_message = self.parsed_cookie['news-message'].value
            message = urllib.unquote_plus(quoted_message)

        else:
            message = None

        self['horsemeat.news_message_cookie'] = message
        return message

    @property
    def news_message_cookie_popped(self):
        return self.get('horsemeat.news_message_cookie_popped')

    def pop_news_message_cookie(self):

        """
        Look up the cookie, record that it has been read, then return
        it.
        """

        if (self.news_message_cookie
            and not self.news_message_cookie_popped):

            self['horsemeat.news_message_cookie_popped'] = True

            s = self.news_message_cookie

            return s

    @property
    def is_AJAX(self):

        return self.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'

    @property
    def address_bar(self):

        """
        Return the best guess for what is in the browser's address bar.

        Of course there's no way to put cookie data in the address bar,
        so this ain't guaranteed to trigger the same effect.
        """

        if self.QUERY_STRING:

            return '{0}://{1}/{2}?{3}'.format(
                self["wsgi.url_scheme"],
                self.host,
                self.PATH_INFO,
                self.QUERY_STRING)

        else:

            return '{0}://{1}/{2}'.format(
                self["wsgi.url_scheme"],
                self.host,
                self.PATH_INFO)

    # aliases
    permalink = address_bar

    @property
    def path_and_qs(self):

        if self.QUERY_STRING:

            return '{0}?{1}'.format(
                self.PATH_INFO,
                self.QUERY_STRING)

        else:

            return self.PATH_INFO


    @property
    def host(self):

        if 'HTTP_X_FORWARDED_HOST' in self:
            return self['HTTP_X_FORWARDED_HOST']

        elif 'HTTP_HOST' in self:
            return self['HTTP_HOST']

        else:
            return self['SERVER_NAME']

    @property
    def line_one(self):

        """
        Returns something like::

            GET /fibityfoo

        or

            POST /bim-bam-boom

        Based on the underlying request.
        """

        return LineOne('{REQUEST_METHOD} {PATH_INFO}'.format(**self))

    @property
    def session(self):

        """
        Return the session if the UUID is in the cookie, and the hexdigest
        checks out, and the database says it ain't expired yet.
        """

        if 'session' in self:
            return self['session']

        elif self.parsed_cookie and 'session_uuid' in self.parsed_cookie:

            session_uuid = self.parsed_cookie['session_uuid'].value
            session_hexdigest = self.parsed_cookie['session_hexdigest'].value

            calculated_hexdigest = hmac.HMAC(
                bytes(
                    str(self.config_wrapper.app_secret),
                    "utf8"),
                bytes(
                    str(session_uuid), "utf8")).hexdigest()

            # Catch session IDs that have been tampered with.  There
            # really ought to be a way to do this in the SQL query,
            # since we're doing something very similar to checking an
            # salted hashed password.

            if session_hexdigest != calculated_hexdigest:
                log.info("Caught a session with an invalid HMAC!")
                self['session_uuid'] = None
                return

            qry = textwrap.dedent("""
                select (s.*)::webapp_sessions as ts
                from webapp_sessions s
                where s.session_uuid = (%s)
                and s.expires > current_timestamp
                """)

            cursor = self.pgconn.cursor()

            cursor.execute(qry, [session_uuid])

            if cursor.rowcount == 1:
                s = cursor.fetchone().ts
                self['session'] = s
                return s

        else:
            self['session'] = None

    @session.setter
    def session(self, sesh):
        self["session"] = sesh

    @property
    def user(self):

        """

        Is either None or is a bunch of data extracted from the
        database.

        When request.user is None, it means this is a user we don't
        know.

        """

        # First check if we already made one.
        if 'user' in self:
            return self['user']

        # If we don't already have a user, see if we can look one up.
        elif self.session and self.session.person_uuid:

            cursor = self.pgconn.cursor()

            cursor.execute(textwrap.dedent("""
                select (p.*)::people as user
                from people p
                where p.person_uuid = (%s)
                """), [self.session.person_uuid])

            row = cursor.fetchone()

            if row:
                self['user'] = row.user
                return self['user']


    @property
    def CONTENT_TYPE(self):
        return self.get('CONTENT_TYPE')

    @property
    def parsed_content_type(self):

        if self.CONTENT_TYPE:
            return cgi.parse_header(self.CONTENT_TYPE)

    @property
    def charset(self):

        """
        Default to UTF-8, but just in case somebody set it otherwise,
        use that.
        """

        if self.parsed_content_type:

            junk, options = self.parsed_content_type
            return options.get('charset', 'UTF-8')

        else:
            return 'UTF-8'


    def get_binder_id(self):

        if 'binder_id' in self:
            return self['binder_id']

        if 'binder_id' in self.wz_req.args:
            self['binder_id'] = int(self.wz_req.args['binder_id'])
            return self['binder_id']

        elif 'binder_id' in self.wz_req.form:
            self['binder_id'] = int(self.wz_req.form['binder_id'])
            return self['binder_id']

        elif self.global_session_data \
        and 'binder_id' in self.global_session_data:
            self['binder_id'] = self.global_session_data['binder_id']
            return self['binder_id']

        else:
            raise ValueError('Sorry, could not figure out binder ID')

    @property
    def json(self):

        if 'json' in self:
            return self['json']

        elif self.body:

            try:
                self['json'] = json.loads(self.body)
                return self.json

            except Exception as ex:
                log.exception(ex)
                self['json'] = None
                return self.json

        else:
            self['json'] = None
            return self.json

    @property
    def client_IP_address(self):

        if 'HTTP_X_FORWARDED_FOR' in self:
            return self['HTTP_X_FORWARDED_FOR'].strip()

        elif 'REMOTE_ADDR' in self:
            return self['REMOTE_ADDR'].strip()


    @property
    def is_JSON(self):

        if self.CONTENT_TYPE:
            return 'json' in self.CONTENT_TYPE.lower()

        else:
            return False

    @property
    def __jsondata__(self):

        return dict(
           is_JSON=self.is_JSON,
           json=self.json if self.is_JSON else None,
           session=self.session,
           user=self.user,
           method=self.REQUEST_METHOD,
           line_one=self.line_one,
        )

class BiggerThanMemoryBuffer(ValueError):

    """
    I raise this exception when the content length is greater than the
    allowed amount to load into memory.
    """

class LineOne(object):

    """
    Pretty much a boring old string, but can be compared against a
    regular expression object in addition to regular old strings.

    >>> LineOne('GET /my-account') == 'GET /my-account'
    True

    >>> LineOne('GET /my-account') == 'GET /login'
    False

    >>> print(LineOne('GET /my-account'))
    GET /my-account

    >>> LineOne('GET /product/99') == re.compile(r'^GET /login')
    False

    Instead of getting True or False back, you get either the match
    object back or False.
    >>> g = LineOne('GET /product/99') == re.compile(r'^GET /product/(\d+)$')
    >>> g.groups()
    ('99',)

    >>> g = LineOne('GET /products/99?json=1') == re.compile(r'^GET /products/(\d+)')
    >>> bool(g)
    True

    >>> LineOne('GET /products/99?json=1') == re.compile(r'^GET /my-account')
    False

    >>> l1 = LineOne('GET /products/99?json=1')

    Test for membership in a list containing strings and regular
    expressions:
    >>> l1 in [
    ...     '/GET /my-account',
    ...     re.compile(r'^GET /p/(\d+)'),
    ...     re.compile(r'GET /products/(\d+)'),
    ... ]
    True

    Right now, testing for membership in a dictionary only works for
    string comparisions, not regex stuff.  Boo!

    But I don't know how to make this work any other way, based on how
    dictionaries work inside.


    >>> l1 in dict([
    ...     (re.compile(r'^GET /p/(\d+)'), 1),
    ...     (re.compile(r'GET /products/(\d+)'), 2),
    ... ])
    False

    """

    def __init__(self, s):
        self.s = s
        self.most_recent_match = None

    def __eq__(self, otherguy):

        if self.s == otherguy:
            return True

        elif hasattr(otherguy, 'match') \
        and inspect.isroutine(otherguy.match):
            self.most_recent_match = otherguy.match(self.s)
            return self.most_recent_match or False

        else:
            return False

    def __str__(self):
        return str(self.s)

    def __hash__(self):
        return hash(self.s)

    def convert_and_match(self, s):

        """
        Convert string s to a regular expression pattern and return the
        match.

        >>> l1 = LineOne('GET /products/99?json=1')
        >>> g = l1.convert_and_match(r'GET /products/(\d+)')
        >>> g.groups()
        ('99',)

        """

        pattern = re.compile(s)
        self.most_recent_match = pattern.match(self.s)

        return self.most_recent_match


    def test_for_match(self, x):
        return self == x

    @property
    def __jsondata__(self):
        return str(self)

