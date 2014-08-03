# vim: set expandtab ts=4 sw=4 filetype=python:

import functools
import json
import pprint
import uuid

__version__ = '2.3.0'

class HorsemeatJSONEncoder(json.JSONEncoder):

    def default(self, obj):

        import psycopg2.extras

        # Any object that wants to be encoded into JSON should make a
        # property called __json__data that spits out some dictionary.
        if hasattr(obj, '__jsondata__'):
            return obj.__jsondata__

        # this is how we handle datetimes and dates.
        elif hasattr(obj, 'isoformat') and callable(obj.isoformat):
            return obj.isoformat()

        elif isinstance(obj, uuid.UUID):
          return str(obj)

        elif isinstance(obj, psycopg2.extras.DateTimeTZRange):
            return dict(lower=obj.lower, upper=obj.upper)

        # Stick your own type check stuff here.
        # End of your own stuff.

        else:
            return json.JSONEncoder.default(self, obj)


fancyjsondumps = functools.partial(
    json.dumps,
    cls=HorsemeatJSONEncoder,
    sort_keys=True,
    indent=4,
    separators=(',', ': '))
