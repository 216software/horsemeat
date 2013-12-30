# vim: set expandtab ts=4 sw=4 filetype=python:

import logging
import os
import smtplib
import socket
import textwrap

log = logging.getLogger(__name__)

class EmailMessageInserter(object):

    def __init__(self, recipient_email_address, message_type):

        self.recipient_email_address = recipient_email_address
        self.message_type = message_type

    @property
    def bound_variables(self):

        return dict(
            recipient_email_address=self.recipient_email_address,
            message_type=self.message_type)

    @property
    def insert_query(self):

        return textwrap.dedent("""
            insert into email_message_queue
            (
                recipient_email_address,
                message_type
            )
            values
            (%(recipient_email_address)s, %(message_type)s)

            returning
            email_message_queue_id,
            nonce,
            recipient_email_address,
            message_type
            """)

    def execute(self, dbconn):

        cursor = dbconn.cursor()

        cursor.execute(self.insert_query, self.bound_variables)

        return cursor.fetchone()


class EmailSender(object):

    def __init__(self, cw, row):

        self.cw = cw
        self.row = row

    def send_email(self):

        pgconn = self.cw.get_pgconn()
        cursor = pgconn.cursor()

        log.debug("Working on row {0}.".format(self.row))

        if self.row.message_type == 'registration':

            s = self.cw.make_smtp_connection()

            s.sendmail(
                'info@{0}'.format(self.cw.host),
                self.row.recipient_email_address,

                textwrap.dedent("""\
                    From: info@{host}
                    Subject: Confirm RegBinder Registration

                    Hi --

                    This is your invitation to RegBinder.

                    To confirm your membership, click the link below or paste it into your browser.

                        {web_host}/confirm-email?email_address={recipient_email_address}&nonce={nonce}

                    For any questions, email info@regulatorybinder.com.

                    The RegBinder team
                    """).format(
                        host=self.cw.host,
                        web_host=self.cw.web_host,
                        recipient_email_address=self.row.recipient_email_address,
                        nonce=self.row.nonce))

            log.info("Just sent an invite email to {0}".format(
                self.row.recipient_email_address))

        elif self.row.message_type == 'forgot password':

            s = self.cw.make_smtp_connection()

            s.sendmail(
                'horsemeat@{host}'.format(host=self.cw.host),
                self.row.recipient_email_address,

                textwrap.dedent("""\
                    From: horsemeat@{host}
                    Subject: Reset RegBinder password

                    Hi --

                    If you want to reset your RegBinder password,
                    click the link below or paste it into your
                    browser.

                        {web_host}/reset-password?email_address={recipient_email_address}&nonce={nonce}

                    If it wasn't you, well, then you can ignore
                    this email, and nothing will happen.

                    Have a nice day!

                    The RegBinder team
                    """).format(
                        host=self.cw.host,
                        web_host=self.cw.web_host,
                        recipient_email_address=self.row.recipient_email_address,
                        nonce=self.row.nonce))

            log.info("Just sent a reset-password email to {0}".format(
                self.row.recipient_email_address))

    # Now mark the message as sent.

        cursor.execute(textwrap.dedent("""
            update email_message_queue
            set sent = current_timestamp
            where email_message_queue_id = %s
            returning email_message_queue_id, updated
            """),
            [self.row.email_message_queue_id])

        email_message_queue_id, updated = cursor.fetchone()

        log.info(
            "Updated message {0} to this updated time: {1}.".format(
                email_message_queue_id, updated))

        return email_message_queue_id
