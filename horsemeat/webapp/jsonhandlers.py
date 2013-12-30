#vim: set expandtab ts=4 sw=4 filetype=python:

import logging

from horsemeat.webapp.framework.handler import Handler
from horsemeat.webapp.framework.response import Response

log = logging.getLogger(__name__)

class GimmeJSON(Handler):

    def route(self, req):

        if req.line_one == 'GET /json/gimme':

            log.debug('Index has got this one')

            return self.handle

    def handle(self, req):

        return Response.json({"test":"hi"})

