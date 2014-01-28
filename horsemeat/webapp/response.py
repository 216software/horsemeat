# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import Cookie
import datetime
import hmac
import json
import logging
import pprint
import urllib

import clepy

from horsemeat import configwrapper

log = logging.getLogger(__name__)

class Response(object):


    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    @property
    def body(self):
        return self._body

    @body.setter
    def body(self, val):

        """
        If the body isn't wrapped in a list, I'll wrap it in a list.
        """

        self._body = clepy.listmofize(val)


    def add_nocache_header(self):

        nocache = ('Cache-Control', 'no-cache')

        if nocache not in self.headers:
            self.headers.append(nocache)

        return self

    def remove_nocache_header(self):

        nocache = ('Cache-Control', 'no-cache')

        while nocache in self.headers:
            pos = self.headers.index(nocache)
            self.headers.pop(pos)

        return self

    @property
    def http_status(self):

        """
        You say tomah-to, I say tomay-to.
        """

        return self.status

    @classmethod
    def RedirectResponse(cls, location, news_message=None):
        """
        Return a 302 redirect response.

        The location parameter should include the scheme and the host
        like this::

        >>> resp = Response.RedirectResponse(
        ...     "http://example.com/fibityfoo")

        >>> resp.status
        '302 FOUND'

        Do not do RELATIVE redirects with this method!  Browsers
        sometimes do weird stuff with them, like add them to the
        existing path!

        Just use the relative_redirect method if you want to do
        something like::

        >>> cw = configwrapper.ConfigWrapper.from_yaml_file_name('test.yaml') # doctest: +SKIP
        >>> cw = cw.set_as_default() # doctest: +SKIP

        >>> resp = Response.relative_redirect('/login') # doctest: +SKIP

        """

        if not location.startswith('http'):

            raise Exception(
                "{0} is a relative redirect!  "
                "Use the relative_redirect classmethod for in-app "
                "redirects".format(location))

        else:


            resp = cls('302 FOUND', [('Location', location)], [])

            if news_message:
                resp.set_news_message_cookie(news_message)

            return resp


    # redirect is an alias.
    redirect = RedirectResponse


    @classmethod
    def relative_redirect(cls, path, news_message=None):

        if path.startswith('http'):

            raise Exception("WRONG: you probably should use "
                "Response.redirect for a location like {0}".format(path))

        else:

            # Look up whatever config file has already been loaded
            # (obviously you need to have already loaded a config file
            # and set it as the default for this to work).
            cw = configwrapper.ConfigWrapper.get_default()

            location = '{0}://{1}{2}'.format(
                cw.scheme,
                cw.host,
                path)

            resp = cls('302 FOUND', [('Location', location)], [])

            if news_message:
                resp.set_news_message_cookie(news_message)

            return resp


    @classmethod
    def PermRedirectResponse(cls, location):
        """
        Return a 301 redirect response.
        """

        return cls('301 Moved Permanently', [('Location', location)], [])

    permRedirect = PermRedirectResponse

    @classmethod
    def html(cls, body):

        """
        Return a 200 OK response with HTML content.
        """

        return cls(
            '200 OK',
            [('Content-Type', 'text/html; charset=utf-8')],
            body)

    @classmethod
    def css(cls, body):
        return cls('200 OK', [('Content-Type', 'text/css')], body)

    @classmethod
    def plain(cls, body):

        # This doctest has to be in unicode.

        u"""
        Example usage:

        >>> resp = Response.plain('hello world!')

        >>> resp.status
        '200 OK'

        >>> resp.headers
        [('Content-Type', 'text/plain')]

        Notice that the body was wrapped in a list:
        >>> resp.body
        ['hello world!']

        But if you pass in stuff already wrapped in a list, I won't
        double-wrap it.
        >>> Response.plain(['body already comes in with a list']).body
        ['body already comes in with a list']

        Unicode strings get encoded to utf8.
        >>> Response.plain(u'Jalapeño').body == [u'Jalapeño'.encode('utf8')]
        True

        """

        if isinstance(body, list):
            s = body[0]
        else:
            s = body

        if isinstance(s, unicode):
            encoded_s = s.encode('utf8')

        else:
            encoded_s = s

        return cls(
            '200 OK',
            [('Content-Type', 'text/plain')],
            encoded_s)

    @classmethod
    def pformat(cls, body):

        return cls(
            '200 OK',
            [('Content-Type', 'text/plain')],
            [pprint.pformat(body)])


    def set_redirect_cookie(self, location):

        """
        Give me a location like 'http://horsemeat.com/my-account' and I'll
        store a cookie like

            redirect-to=http://horsemeat.com/my-account

        The idea is that some other app code will look for this cookie
        and then do a redirect to that address.

        Each call to this method overwrites the stored cookie.
        """

        if self.redirect_cookie:
            self.remove_redirect_cookie_header()

        c = ('Set-Cookie', 'redirect-to=%s' % location)

        self.headers.append(c)


    def set_relative_redirect_cookie(self, path):

        """
        Similar to set_redirect_cookie, but works with relative
        redirects like "/login".
        """

        if self.redirect_cookie:
            self.remove_redirect_cookie_header()

        cw = configwrapper.ConfigWrapper.get_default()

        location = '{0}://{1}{2}'.format(
            cw.scheme,
            cw.host,
            path)

        c = ('Set-Cookie', 'redirect-to={0}'.format(location))

        self.headers.append(c)




    @property
    def redirect_cookie(self):

        redirect_cookie_headers = [h for h in self.headers
            if h[0] == 'Set-Cookie'
            and h[1].startswith('redirect-to')]

        if redirect_cookie_headers:
            return redirect_cookie_headers[0]

    def remove_redirect_cookie_header(self):

        """
        This does NOT expire it on the client, so don't be stupid!

        You have to use expire_redirect_cookie to tell the browser (the
        client) to stop sending the redirect-to browser.

        This method is for internal use, so that I can prevent adding
        redundant cookie headers.
        """

        if self.redirect_cookie:
            pos = self.headers.index(self.redirect_cookie)
            self.headers.pop(pos)

        return self

    def expire_redirect_cookie(self):

        """
        The app code that sends the redirect also needs to tell the
        browser to expire the redirect cookie.
        """

        if self.redirect_cookie:

            raise Exception("First you set a redirect cookie, now "
                "you're expiring it?  Make up your mind...")

        self.remove_redirect_cookie_header()

        c = Cookie.SimpleCookie()

        c['redirect-to'] = 'expired'
        c['redirect-to']['expires'] = self.two_weeks_ago

        self.headers.append(
            ('Set-Cookie', c.output(header='').strip()))

        return self

    @property
    def two_weeks_ago(self):
        return (
            datetime.datetime.now()
            - datetime.timedelta(days=14)).strftime(
                '%a, %d %b %Y %H:%M:%S')


    @classmethod
    def redirect_from_cookie(cls, request):

        """
        Read the redirect-to cookie out of the request, make a redirect
        response, and add the expire_redirect_cookie() to it.
        """

        self = cls.redirect(request.redirect_cookie)
        self.expire_redirect_cookie()

        return self

    @classmethod
    def json(cls, data, status='200'):

        if status == '400':
            response_status = '400 Bad Request'
        elif status == '404':
            response_status = '400 Not Found'
        else:
            response_status = '200 OK'

        json_response = cls(
            response_status,
            [('Content-Type', 'application/json')],
            json.dumps(data, cls=configwrapper.ComplexEncoder))

        return json_response

    def set_news_message_cookie(self, messagetext, hmac_secret=None):

        quoted_messagetext = urllib.quote_plus(messagetext)

        c = Cookie.SimpleCookie()

        c['news-message'] = quoted_messagetext
        c['news-message']['httponly'] = True
        c['news-message']['path'] = '/'

        self.headers.append((
            'Set-Cookie',
            c.output(header='').strip()))

        if hmac_secret:

            self.headers.append((
                'Set-Cookie',
                'news-message-hexdigest={0};'.format(hmac.HMAC(
                    hmac_secret,
                    quoted_messagetext).hexdigest())))

        return self

    def mark_news_message_as_expired(self):

        c = Cookie.SimpleCookie()

        c['news-message'] = 'Sorry'
        c['news-message']['expires'] = self.two_weeks_ago
        c['news-message']['httponly'] = True
        c['news-message']['path'] = '/'

        self.headers.append(
            ('Set-Cookie', c.output(header='').strip()))

        return self

    @classmethod
    def csv(cls, data):

        return cls(
            '200 OK',
            [('Content-Type', 'text/csv')],
            data)

    @classmethod
    def template(cls, template, **data):
        x = template.render(**data)
        return cls.html([x.encode('utf8')])

    @classmethod
    def tmpl(cls, template_name, **data):

        cw = configwrapper.ConfigWrapper.get_default()

        j = cw.get_jinja2_environment()

        template = j.get_template(template_name)

        log.debug('Rendering template {0}...'.format(template_name))

        x = template.render(**data)

        return cls.html(x.encode('utf8'))

    def set_session_cookie(self, session_id, secret):

        c = Cookie.SimpleCookie()
        c['session_id'] = session_id
        c['session_hexdigest'] = hmac.HMAC(secret, str(session_id)).hexdigest()

        self.headers.append(('Set-Cookie', c.output(header='').strip()))

