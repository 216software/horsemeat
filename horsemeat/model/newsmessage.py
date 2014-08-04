# vim: set expandtab ts=4 sw=4 filetype=python:

import logging
import textwrap

log = logging.getLogger(__name__)

class NewsMessageQueryMaker(object):

    """
    Wondering if it makes some sense for news message to have
    a sense of what handler added it to the db. not necessary
    for displaying the message, but might be helpful for debugging
    or when we want to show all actions taken
    """
    def __init__(self, news_message, session_uuid ):

        self.news_message = news_message
        self.session_uuid = session_uuid

    @property
    def insert_query(self):

        return textwrap.dedent("""
            insert into news_messages
            (
                session_uuid,
                news_message
            )

            values
            (
                %(session_uuid)s,
                %(news_message)s
            )

            returning news_message_id""")

    @property
    def bound_variables(self):

        return dict(
            session_uuid=self.session_uuid,
            news_message=self.news_message)

    def insert(self, dbconn):

        cursor = dbconn.cursor()

        cursor.execute(self.insert_query, self.bound_variables)

        self.news_message_id = cursor.fetchone()

        return self.news_message_id


"""

Pop the most recent message from this session.
Return message and set the message has_read
to false
"""
def pop_news_message(pgconn, session_uuid):

    try:

        pgconn.execute(textwrap.dedent("""

            select news_message_id, news_message
            from news_messages
            where session_uuid = %s and has_been_read = false
            order by inserted
            desc limit 1;
        """), [session_uuid])

        values = pgconn.cursor.fetchone()

        return values['news_message']


    except Exception as e:
        log.critical("Tried to pop a message. nothing there")

        return None




