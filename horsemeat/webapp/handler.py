# vim: set expandtab ts=4 sw=4 filetype=python:

import abc
import datetime
import logging
import sys
import textwrap
import warnings

import clepy
import decorator
import jinja2

log = logging.getLogger(__name__)

module_template_prefix = 'framework'
module_template_package = 'horsemeat.webapp.framework.framework_templates'

class Handler(object):

    __metaclass__ = abc.ABCMeta

    add_these_to_jinja2_globals = dict()

    route_patterns = []

    route_strings = set()

    # Subclasses must point this at something besides None!
    Response = None

    def __init__(self, config_wrapper, dispatcher):

        self.config_wrapper = config_wrapper
        self.dispatcher = dispatcher

        self.add_stuff_to_jinja2_globals()
        self.add_module_template_folder_to_jinja2_environment()

    @property
    def cw(self):
        return self.config_wrapper

    def add_stuff_to_jinja2_globals(self):

        if self.add_these_to_jinja2_globals:

            for k, v in self.add_these_to_jinja2_globals.items():
                self.j.globals[k] = v

        # In general, when I modify self, I return it.
        return self


    def add_module_template_folder_to_jinja2_environment(self):

        m = sys.modules[self.__module__]

        if hasattr(m, 'module_template_prefix') \
        and hasattr(m, 'module_template_package'):

            # Throw an exception if I'm going to overwrite something!

            package_name, template_folder = \
            m.module_template_package.rsplit('.', 1)

            self.j.loader.mapping[m.module_template_prefix] = \
            jinja2.PackageLoader(
                package_name,
                template_folder)

    @property
    def j(self):
        return self.cw.get_jinja2_environment()

    @property
    def templates(self):
        return self.cw.get_jinja2_environment()

    @property
    def pgconn(self):
        return self.cw.get_pgconn()

    @abc.abstractmethod
    def route(self, request):
        """
        Subclasses must define me!
        """

        raise NotImplementedError


    @abc.abstractmethod
    def handle(self, request):
        """
        Subclasses must define me!
        """

        raise NotImplementedError

    def prompt_for_login(self, req):

        # if ajax request, relative redirect won't work well
        # throw 401 error for now until we can figure out
        # better way to do it.

        # 401 error will be caught by jquery ajax error handler
        if req.is_AJAX:
            resp = self.Response.plain("You have to log in first!")

            resp.status = '401 UNAUTHORIZED'

        if req.is_JSON:
            resp = self.Response.json(dict(
                reply_timestamp=datetime.datetime.now(),
                message="You have to log in first!",
                success=False))

            resp.status = '401 UNAUTHORIZED'


        else:
            resp = self.Response.relative_redirect('/login',
                'You have to log in first!')

            # Redirect back to the page the person is hitting right now.
            resp.set_redirect_cookie(req.address_bar)

        return resp


    def ask_to_authenticate_first(self, redirect_location, message):

        ### Should we just destroy this?  I vote yes.

        """

        This is a yucky implementation, but the idea is to be able to
        redirect somebody somewhere with a custom message, and be able
        to do this in the route method.

        Consider it like a fancier version of "prompt for login" and use
        it like this::

            def route(self, req):
                if req.line_one == '...':
                    if self.has_sufficient_credentials(req.user):
                        return self.handle
                    else:
                        return self.ask_to_authenticate_first(
                            '/this-page',
                            'Sorry, you need XXX credential first')

        """

        def f(req):

            resp = self.Response.relative_redirect('/login', message)
            resp.set_redirect_cookie(redirect_location)
            return resp

        return f

    @abc.abstractproperty
    def four_zero_four_template(self):
        raise NotImplementedError

    def not_found_AJAX(self, req):

        resp = self.Response.plain("404 NOT FOUND")
        resp.status = '404 NOT FOUND'

        return resp

    def not_found_JSON(self, req):

        resp = self.Response.json(dict(
            reply_timestamp=datetime.datetime.now(),
            message="404 NOT FOUND '{0}'".format(req.line_one),
            success=False))

        resp.status = '404 NOT FOUND'

        return resp

    def not_found_HTML(self, req):

        resp = self.Response.tmpl(self.four_zero_four_template)

        resp.status = '404 NOT FOUND'

        return resp


    def not_found(self, req):

        """
        Use this when you KNOW you should reply with a 404.

        Otherwise, just return None out of the route method and let the
        NotFound handler catch the request.

        """

        #Determine what we return based on request type
        if req.is_AJAX:
            return self.not_found_AJAX(req)

        if req.is_JSON:
            return self.not_found_JSON(req)

        else:
            return self.not_found_HTML(req)


    def check_route_patterns(self, req):

        """
        Example usage::

            class MyHandler(Handler):

                route_patterns = list([
                    re.compile(r"GET /my-handler/(?P<club_number>\d+)")
                ])

                route = Handler.check_route_patterns

                def handle(self, req):

                    return self.Response.json(dict(
                        message="You asked about club {0}".format(
                            req["club_number"]),
                        success=True,
                        reply_timestamp=datetime.datetime.now()))

        """

        if not self.route_patterns:
            raise Exception("You need some route patterns!")

        for rp in self.route_patterns:

            if not hasattr(rp, "match"):
                log.warning("This pattern {0!r} might not work right because it has no match method (i.e., it isn't a regex!).  You probably forgot to wrap it in re.compile...".format(rp))

            match = req.line_one.test_for_match(rp)

            if match:

                d = match.groupdict()
                for k in d:
                    req[k] = d[k]

                return self.handle

    def check_route_strings(self, req):

        if not self.route_strings:
            raise Exception("You need to define some route strings!")

        if req.line_one in self.route_strings:
            return self.handle

    @property
    def handler_namespace(self):

        return '{0}.{1}'.format(
            self.__class__.__module__,
            self.__class__.__name__)


    def on_startup(self):

        """
        Subclasses MAY fill this in if they want to do
        run some code on startup.

        But they don't have to define it if they don't want to.
        """

        pass

    @staticmethod
    @decorator.decorator
    def only_allow_superusers(handle_method, self, req):

        """
        Add this to a handle method like this::

            @Handler.only_allow_superusers
            def handle(self, req):
                ...

        And then, if the request isn't from a signed-in superuser,
        they'll get a JSON reply below.

        If the request is from a signed-in superuser, then your handle
        method is normal.
        """

        if not req.user or not req.user.is_superuser:

            return Response.json(dict(
                message="Sorry, superusers only!",
                success=False,
                reply_timestamp=datetime.datetime.now()))

        else:
            return handle_method(self, req)

    @property
    def four_zero_four_template(self):
        return 'framework_templates/404.html'

    @staticmethod
    @decorator.decorator
    def require_login(handler_method, self, req):

        """
        Add this to a handle method like this::

            @Handler.require_login
            def handle(self, req):
                ...

        And then, if the request isn't from a signed-in user,
        they'll get the JSON reply below.

        If the request is from a signed-in user, then your handle
        method is normal.
        """

        if not req.user:

            return Response.json(dict(
                reply_timestamp=datetime.datetime.now(),
                message="Sorry, you need to log in first!",
                needs_to_log_in=True,
                success=False))

        else:
            return handler_method(self, req)


    @staticmethod
    @decorator.decorator
    def get_session_from_cookie_or_json(handler_method, self, req):

        if req.user:
            return handler_method(self, req)

        elif req.json and "session_uuid" not in req.json:

            sesh = pg.sessions.Session.verify_session_uuid(
                self.cw.get_pgconn(),
                req.json["session_uuid"])

        if sesh:
            return handler_method(self, req)

        else:

            return Response.json(dict(
                reply_timestamp=datetime.datetime.now(),
                message="Sorry, you need to log in first!",
                needs_to_log_in=True,
                success=False))

    required_json_keys = []

    def check_all_required_keys_in_json(self, req):
        return all(k in req.json for k in self.required_json_keys)

    def find_missing_json_keys(self, req):
        return [k for k in self.required_json_keys if k not in req.json]


    @staticmethod
    @decorator.decorator
    def require_json(handler_method, self, req):

        """
        Add this to a handle method like this::

            required_json_keys = ['A', 'B']

            @Handler.require_json
            def handle(self, req):
                ...

        And then, if the request isn't a JSON request with keys A and B,
        they'll get the JSON reply below.

        """

        if not req.is_JSON \
        or not req.json:

            return self.Response.json(dict(
                reply_timestamp=datetime.datetime.now(),
                message="Sorry, I need Content-Type application/json!",
                success=False))

        elif not self.check_all_required_keys_in_json(req):

            missing_json_keys = self.find_missing_json_keys(req)

            log.warn("Request {0} didn't have these keys: {1}".format(
                req.line_one,
                missing_json_keys))

            return self.Response.json(dict(
                success=False,
                reply_timestamp=datetime.datetime.now(),
                message="Sorry, you are missing keys: [{0}]!".format(
                    ", ".join(self.find_missing_json_keys(req)))))

        else:
            return handler_method(self, req)

    required_user_groups = []

    def check_user_group_in_required_groups(self, req):
        return req.user.group_title in self.required_user_groups

    @staticmethod
    @decorator.decorator
    def require_group(handler_method, self, req):

        """
        Add this to a handle method like this::

            required_groups = ['administrator', 'supervisor']

            @Handler.require_group
            def handle(self, req):
                ...

        And then, if the request user isn't in the group 'administrator'
        or 'supervisor',
        they'll get the JSON reply below.

        """

        if not self.check_user_group_in_required_groups(req):

            return self.Response.json(dict(
                reply_timestamp=datetime.datetime.now(),
                message="Sorry, you are are not in the group: [{0}]!".format(
                    ",".join(self.required_user_groups))))

        else:
            return handler_method(self, req)


    @staticmethod
    @decorator.decorator
    def get_session_from_cookie_or_json_or_QS(handler_method, self, req):

        """
        You can test this like so::

            $ curl --data '{"session_uuid": "d5e19089-ce27-4ab9-b1d0-129a19c81a94"}' -H "Content-Type: application/json" http://circuit.xps/api/insert-club-fee

            $ curl http://circuit.xps/api/insert-club-fee?"session_uuid=d5e19089-ce27-4ab9-b1d0-129a19c81a94"

            $ curl 'http://circuit.xps/api/insert-club-fee' -H 'Cookie: session_uuid=d5e19089-ce27-4ab9-b1d0-129a19c81a94; session_hexdigest=162719e3a569b048b005d6d5140fe884'

        """

        found_session = False

        if req.user:
            found_session = True

        elif req.json and "session_uuid" in req.json:

            sesh = pg.sessions.Session.verify_session_uuid(
                self.cw.get_pgconn(),
                req.json["session_uuid"])

            if sesh:
                found_session = True

        elif req.wz_req.args and "session_uuid" in req.wz_req.args:

            sesh = pg.sessions.Session.verify_session_uuid(
                self.cw.get_pgconn(),
                req.wz_req.args["session_uuid"])

            if sesh:
                found_session = True

        if found_session:
            return handler_method(self, req)

        else:

            return self.Response.json(dict(
                reply_timestamp=datetime.datetime.now(),
                message="Sorry, you need to log in first!",
                needs_to_log_in=True,
                success=False))
