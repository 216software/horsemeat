# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf-8:
# -*- coding: utf-8 -*-

import abc
import datetime
import importlib
import inspect
import logging
import pdb
import sys
import warnings
import traceback

import jinja2
import werkzeug.debug

from horsemeat import configwrapper
from horsemeat.webapp.handler import Handler
from horsemeat.webapp.request import Request
from horsemeat.webapp.response import Response

log = logging.getLogger(__name__)

# Tell python to always SHOW the deprecation warnings.
warnings.filterwarnings('always', category=DeprecationWarning)

class Dispatcher(object):

    """
    This is the webapp that gunicorn talks to.
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self, jinja2_environment, dbconn, config_wrapper):

        self.jinja2_environment = jinja2_environment
        self.dbconn = dbconn
        self.config_wrapper = config_wrapper

        self.handlers = []
        self.make_handlers()

        self.error_page = self.jinja2_environment.get_template(
            'framework_templates/error.html')

        log.info("Dispatcher __init__ complete!  Framework is ready.")

    @property
    def cw(self):
        return self.config_wrapper

    @property
    def pgconn(self):
        return self.dbconn

    def __call__(self, environ, start_response):

        """
        This is the WSGI app interface.

        Every time a request hits gunicorn, this method fires.
        """

        try:

            req = Request(self.dbconn, self.config_wrapper, environ)

            # TODO: Figure out if there is some more elegant approach to
            # making the request object visible in the template.
            self.jinja2_environment.globals['request'] = req
            self.jinja2_environment.globals['req'] = req

            log.info('Got request {0} {1}'.format(
                req.REQUEST_METHOD, req.path_and_qs))

            handle_function = self.dispatch(req)

            resp = handle_function(req)

            if not isinstance(resp, Response):
                raise Exception("Handler didn't return a response object!")

            # TODO: make this happen as an automatic side effect of
            # reading the data, so that there is absolutely no risk at
            # all of forgetting to do this.
            if req.news_message_cookie_popped:
                resp.mark_news_message_as_expired()

            # Update the signed-in user's session expires column.
            if req.user:

                new_expires_time = req.session.maybe_update_session_expires_time(
                    self.pgconn)

            self.dbconn.commit()

            start_response(resp.status, resp.headers)

            log.info('Replying with status %s.\n' % resp.status)

            if resp.status.startswith('30'):
                log.info('Redirecting to {0}.'.format(resp.headers))

            return resp.body

        except Exception, ex:

            self.dbconn.rollback()
            log.critical(ex, exc_info=1)

            if self.cw.launch_debugger_on_error:
                raise

            else:

                log.critical('address bar: {0}'.format(req.address_bar))
                log.critical('post body: {0}'.format(req.wz_req.form))

                log.critical(environ)

                start_response(
                    '500 ERROR',
                    [('Content-Type', 'text/html; charset=utf-8')],
                    sys.exc_info())

                s = self.error_page.render()

                return [s.encode('utf8')]


    def dispatch(self, request):

        """
        Return the first handler that wants to handle this request.

        Fun fact -- in your handler's route method, you can
        return any callable object, not necessarilly self.handle.

        So the router can inspect 100% of the incoming data and decide
        if it should dispatch to its handle_good_data method or the
        handle_invalid_data method.

        """

        for candidate in self.handlers:

            thing = candidate.route(request)

            if thing:

                # Check if we got a function back.  This is the
                # preferred behavior.
                if callable(thing):

                    log.info(
                        'Dispatching to {0}.{1}.{2}.'.format(
                        candidate.__class__.__module__,
                        candidate.__class__.__name__,
                        thing.__name__,
                    ))

                    return thing

                # Check if the thing we got has a thing.handle method.
                elif inspect.ismethod(getattr(thing, 'handle', None)):

                    warnings.warn(
                        'Return self.handle rather than self',
                        DeprecationWarning)

                    log.info(
                        'Dispatching to {0}.{1}.{2}.'.format(
                        candidate.__class__.__module__,
                        candidate.__class__.__name__,
                        thing.handle.im_func.func_name,
                    ))

                    return thing.handle

    @classmethod
    def app_from_yaml(cls, yaml_file_name):

        try:
            cw = configwrapper.ConfigWrapper.from_yaml_file_name(
                yaml_file_name)

            # Now, other people can get a reference this by using
            # configwrapper.ConfigWrapper.get_default().
            cw.set_as_default()

            cw.configure_logging()
            cw.verify_config_file()
            cw.connect_everything()

            if cw.production_mode:

                from horsemeat import junkdrawer

                junkdrawer.set_CORS_headers_on_all_containers(
                    cw.get_pyrax_connection(),
                    cw.web_host)

        except Exception, ex:
            traceback.print_exc()
            raise

        try:

            j = cw.get_jinja2_environment()
            pgconn = cw.get_postgresql_connection()

            if cw.launch_debugger_on_error:

                return werkzeug.debug.DebuggedApplication(
                    cls(j, pgconn, cw),
                    evalex=True)

            else:
                return cls(j, pgconn, cw)

        except Exception, ex:
            log.critical(ex, exc_info=1)
            raise

    def make_handler(self, s):

        cls = self.convert_string_to_class(s)

        return cls(
            self.jinja2_environment,
            self.dbconn,
            self.config_wrapper,
            self)


    @staticmethod
    def convert_string_to_class(s):

        """
        Give me a string like 'a.b.c.d.e', and I will return the object
        e from within module a.b.c.d.e.

        The object e can be a class, a function, a dictionary, whatever.

        I had to write this because __import__ allows dynamic **module**
        imports, but not dynamic object imports from within modules.

        Example usage::

        >>> f = Dispatcher.convert_string_to_class('os.path.join')
        >>> import os
        >>> f is os.path.join
        True

        I got this trick from this stack overflow page:

        http://stackoverflow.com/questions/2179251/dynamically-import-a-callable-given-the-full-module-path

        """

        module_name, irrelevant_junk, class_name = s.rpartition('.')

        m = importlib.import_module(module_name)

        obj = getattr(m, class_name)

        return obj


    def make_handlers_from_module_string(self, s):

        m = importlib.import_module(s)

        return [cls(
                self.jinja2_environment,
                self.dbconn,
                self.config_wrapper,
                self)
            for name, cls in inspect.getmembers(m)

            if cls != Handler # don't instantiate the base class!

            and inspect.isclass(cls)
            and issubclass(cls, Handler)

            # This is nasty -- I'm testing if this cls has a route
            # method that has been defined.
            and getattr(cls.route, '__isabstractmethod__', False) is False
            ]

    @abc.abstractmethod
    def make_handlers(self):

        raise NotImplementedError
