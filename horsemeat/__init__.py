# vim: set expandtab ts=4 sw=4 filetype=python:

import decimal
import functools
import json
import pprint
import uuid

from horsemeat.version import __version__

class HorsemeatJSONEncoder(json.JSONEncoder):

    def default(self, obj):

        # TODO: when something can not be JSON-encoded, just return a
        # message like "can not JSON-encode {0}".

        import psycopg2.extras

        # Any object that wants to be encoded into JSON should make a
        # property called __jsondata__ that spits out something that can
        # be JSON-encoded.
        if hasattr(obj, '__jsondata__'):
            return obj.__jsondata__

        # This is to handle datetimes and dates.
        elif hasattr(obj, 'isoformat') and callable(obj.isoformat):
            return obj.isoformat()

        elif isinstance(obj, uuid.UUID):
          return str(obj)

        elif isinstance(obj, (
            psycopg2.extras.DateTimeTZRange,
            psycopg2.extras.DateTimeRange,
            psycopg2.extras.DateRange,
            )):

            return dict(lower=obj.lower, upper=obj.upper)

        elif isinstance(obj, decimal.Decimal):
            return float(obj)

        # Stick your own type check stuff here.
        # End of your own stuff.

        else:
            return json.JSONEncoder.default(self, obj)


# TODO: add a docstring on this guy.
fancyjsondumps = functools.partial(
    json.dumps,
    cls=HorsemeatJSONEncoder,
    sort_keys=True,
    indent=4,
    separators=(',', ': '))



class CookieWrapper:

    """
    This CookieWrapper allows us to be backwards compatible with https
    SimpleCookie.

    We need to switch to werkzeug cookie because google and facebook
    have recently been using malformed cookies, which breaks the reading
    of our cookies

    """


    def __repr__(self):
        return str(self._cookies)

    def __init__(self, cookie_dict):
        self._cookies = cookie_dict

    def __getitem__(self, key):
        return MockMorsel(self._cookies[key])

    def __contains__(self, key):
        return key in self._cookies

    def get(self, key, default=None):
        value = self._cookies.get(key, default)
        return MockMorsel(value) if value is not None else None

class MockMorsel:
    def __init__(self, value):
        self.value = value
