# vim: set expandtab ts=4 sw=4 filetype=python:

import urlparse

class BogusRequest(object):

    """

    This class is for testing.  I'll keep adding stuff as I need it.

    Later, I might figure out how to make this some kind of subclass or
    constructor for the regular request object, so that not too much has
    to be redefined.

    But that's not as easy as I thought it would be.
    """

    def __init__(self, REQUEST_METHOD, HTTP_HOST, PATH_INFO,
        QUERY_STRING, session=None):

        self.REQUEST_METHOD = REQUEST_METHOD
        self.HTTP_HOST = HTTP_HOST
        self.PATH_INFO = PATH_INFO
        self.QUERY_STRING = QUERY_STRING
        self.session = session

    @classmethod
    def from_URL(cls, url):

        """

        >>> url = ('http://sprout.horsemeat.com/do-everything'
        ...     '?earliest_possible_start=2012-06-27T11%3A45'
        ...     '&appointment_start_time=30'
        ...     '&appointment_stop_time=85')

        >>> req = BogusRequest.from_URL(url)

        >>> req.is_GET
        True

        >>> req.parsed_QS['appointment_stop_time']
        ['85']

        """

        parts = urlparse.urlparse(url)

        return cls('GET', parts.netloc, parts.path, parts.query)

    @property
    def is_GET(self):
        return self.REQUEST_METHOD == 'GET'


    @property
    def parsed_QS(self):

        if self.QUERY_STRING:
            return urlparse.parse_qs(self.QUERY_STRING)

        else:
            return {}

    @classmethod
    def from_line_one(cls, line_one):

        """
        >>> req = BogusRequest.from_line_one('GET /do-everything')

        >>> req.is_GET
        True

        >>> req.PATH_INFO
        '/do-everything'

        >>> req.line_one
        'GET /do-everything'

        >>> req = BogusRequest.from_line_one('GET /do-everything?aaa=99')

        >>> req.is_GET
        True

        >>> req.PATH_INFO
        '/do-everything'

        >>> req.line_one
        'GET /do-everything'

        >>> req.parsed_QS['aaa']
        ['99']

        """

        REQUEST_METHOD, PATH_AND_QS = line_one.split(' ')

        if '?' in PATH_AND_QS:
            PATH_INFO, QUERY_STRING = PATH_AND_QS.split('?')

        else:
            PATH_INFO = PATH_AND_QS
            QUERY_STRING = None

        return cls(REQUEST_METHOD, None, PATH_INFO, QUERY_STRING)


    @property
    def line_one(self):

        return '{0} {1}'.format(self.REQUEST_METHOD, self.PATH_INFO)

    @property
    def authenticated_user(self):
        return self.session

    @property
    def logged_in(self):
        return self.session

    @property
    def session(self):
        return self._session

    @session.setter
    def session(self, val):

        if val:
            self._session = val

        else:
            self._session = None

    @property
    def news_message_cookie(self):
        return False

