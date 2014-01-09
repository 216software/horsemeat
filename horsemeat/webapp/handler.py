# vim: set expandtab ts=4 sw=4 filetype=python:

import abc
import logging
import sys
import textwrap

import clepy
import decorator
import jinja2

from horsemeat.webapp.response import Response

log = logging.getLogger(__name__)

module_template_prefix = 'framework'
module_template_package = 'horsemeat.webapp.framework.framework_templates'

class Handler(object):

    __metaclass__ = abc.ABCMeta

    add_these_to_jinja2_globals = dict()

    route_patterns = []

    route_strings = set()

    def __init__(self, jinja2_environment, pgconn, config_wrapper,
    dispatcher):

        self.jinja2_environment = jinja2_environment
        self.pgconn = pgconn
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
                log.debug('Adding {0} to jinja2 globals...'.format(k))
                self.j.globals[k] = v

        # In general, when I modify self, I return it.
        return self

    def add_module_template_folder_to_jinja2_environment(self):

        m = sys.modules[self.__module__]

        if hasattr(m, 'module_template_prefix') \
        and hasattr(m, 'module_template_package'):

            package_name, template_folder = \
            m.module_template_package.rsplit('.', 1)

            self.j.loader.mapping[m.module_template_prefix] = \
            jinja2.PackageLoader(
                package_name,
                template_folder)


    @property
    def j(self):
        return self.jinja2_environment

    @property
    def templates(self):
        return self.jinja2_environment

    @abc.abstractmethod
    def route(self, request):
        """
        Subclasses must define me!
        """

    @abc.abstractmethod
    def handle(self, request):
        """
        Subclasses must define me!
        """

    def prompt_for_login(self, req):

        # if ajax request, relative redirect won't work well
        # throw 401 error for now until we can figure out
        # better way to do it.

        # 401 error will be caught by jquery ajax error handler
        if req.is_AJAX:
            resp = Response.plain("You have to log in first!")

            resp.status = '401 UNAUTHORIZED'

        else:
            resp = Response.relative_redirect('/login',
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

            resp = Response.relative_redirect('/login', message)
            resp.set_redirect_cookie(redirect_location)
            return resp

        return f

    def not_found(self, req):

        """
        Use this when you KNOW you should reply with a 404.

        Otherwise, just return None out of the route method and let the
        NotFound handler catch the request.

        """

        #Determine what we return based on request type
        if req.is_AJAX:
            resp = Response.plain("404 NOT FOUND")
        else:
            resp = Response.tmpl('framework/404.html')

        resp.status = '404 NOT FOUND'

        return resp


    def build_nav_dict(self, binder_id):

        cursor = self.pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select bt.root_folder_id
            from binder_templates bt
            join binders b
            on bt.binder_template_id = b.binder_template_id
            where b.binder_id = %(binder_id)s
            """), {'binder_id': binder_id})

        root_folder_id = cursor.fetchone().root_folder_id

        cursor.execute(textwrap.dedent("""
            select fwc.*, f.folder_title
            from folders_with_children fwc
            join folders f
            on fwc.folder_id = f.folder_id
            order by f.folder_title
            """))

        self.nav_dict = {x.folder_id:x for x in cursor.fetchall()}

        top_node = self.nav_dict[root_folder_id]

        return dict(
            key_function=lambda folder_id: self.nav_dict[folder_id].folder_title,
            structure=self.nav_dict,
            parentchildren=top_node.children)


    def check_route_patterns(self, req):

        for rp in self.route_patterns:
            match = req.line_one.test_for_match(rp)

            if match:

                d = match.groupdict()
                for k in d:
                    req[k] = d[k]

                return self.handle

    def check_route_strings(self, req):

        if req.line_one in self.route_strings:
            return self.handle

    @property
    def handler_namespace(self):

        return '{0}.{1}'.format(
            self.__class__.__module__,
            self.__class__.__name__)


    def build_bread_crumb_dict(self, folder_id):

        cursor = self.cw.get_pgconn().cursor()

        cursor.execute(textwrap.dedent("""
            select folder_id, folder_title, folder_format->'Title' as
            title,
            parent_folder_id

            from folders

            where folder_id = any(get_all_folder_parents(%(folder_id)s))
            """), {'folder_id': folder_id})

        return {row.folder_id:row for row in cursor}


    def build_bread_crumb_data(self, folder_id):

        cursor = self.cw.get_pgconn().cursor()

        cursor.execute(textwrap.dedent("""
            select folder_id, folder_title, folder_format->'Title' as
            title,
            parent_folder_id

            from folders

            where folder_id = any(get_all_folder_parents(%(folder_id)s))
            or folder_id = %(folder_id)s
            """), {'folder_id':folder_id})

        return sorted(cursor.fetchall(), key=lambda row:row.folder_id)


@decorator.decorator
def ask_for_login_if_anonymous(handle, h, req):

    """
    This decorator might cause too much confusion, and if you put it
    on the route, not the handle method, you'll cause all sorts of bugs
    by intercepting a request meant for some other handler.

    On the plus side, it might be nice to have a conventional way to
    test for a logged-in user (given that the req.line_one stuff
    matches).

    And, it could support some introspection.  In other words, we could
    ask a handler "do you have the ask_for_login_if_anonymous
    decorator?"

    """

    if req.user:
        return handle(h, req)

    else:
        return h.prompt_for_login(req)
