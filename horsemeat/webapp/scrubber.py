# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import logging
import re
import textwrap

log = logging.getLogger(__name__)

class Scrubber(object):

    """
    Sub-class me and then define your own scrub method.

    Use a scrubber to extract data from the request.

    For a lot of URLs, a scrubber could really just be a helper method
    on the handler, but some times, you need to do some pretty
    complex data validation.

    So, having a separate class makes it a little easier to organize
    code related to parsing and validating the request from the other
    code involved in a handler.

    """

    def __init__(self, pgconn, req):
        self.pgconn = pgconn
        self.req = req

    def generic_extract(self, raw_data, errors, values, what, from_where,
        required_field, converter=None):

        if what in from_where:
            raw_value = from_where[what][0]
            raw_data[what] = raw_value

            if converter:
                try:
                    values[what] = converter(raw_value)

                except Exception as ex:
                    log.exception(ex)
                    errors[what] = "This doesn't look right"

            else:
                values[what] = raw_value

        elif required_field:
            errors[what] = 'This is a required field!'

            errors['general'] = 'Sorry, you have some bad data'

        return raw_data, errors, values

    @staticmethod
    def convert_empty_strings_to_None(s):

        """
        >>> Scrubber.convert_empty_strings_to_None('') is None
        True

        >>> Scrubber.convert_empty_strings_to_None('99')
        '99'

        >>> Scrubber.convert_empty_strings_to_None(' ')
        ' '

        """

        if s:
            return s

    @staticmethod
    def validate_email_address(s):

        """
        >>> Scrubber.validate_email_address('matt@tplus1.com')
        'matt@tplus1.com'

        I'm not verifying that this is a valid domain.
        >>> Scrubber.validate_email_address('a@b.zzz')
        'a@b.zzz'

        >>> try:
        ...     Scrubber.validate_email_address('a@b')
        ... except Exception as ex:
        ...     print "bad email!"
        bad email!

        """

        email_pattern = re.compile(r'.+@.+\..+')

        if email_pattern.match(s):
            return s

        else:
            raise InvalidEmailAddress(s)


class InvalidEmailAddress(Exception):

    """
    String doesn't look much like an email address
    """
