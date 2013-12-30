#vim: set expandtab ts=4 sw=4 filetype=python:

"""

The only handlers in here are ones we're likely to use on other
projects.

"""

import logging
import textwrap

from horsemeat.webapp.handler import Handler
from horsemeat.webapp.response import Response

log = logging.getLogger(__name__)

module_template_prefix = 'framework'
module_template_package = 'horsemeat.webapp.framework.framework_templates'

class NotFound(Handler):

    def route(self, req):
        return self.handle

    def handle(self, req):
        return self.not_found(req)
