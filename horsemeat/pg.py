# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import logging

log = logging.getLogger(__name__)

class RelationWrapper(object):

    @property
    def __jsondata__(self):
        return self.__dict__

    def get_current_status(self, pgconn):

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select {0}.*::{0} as current_status
            from {0}
            where {0}.{1} = %(pk)s
            and current_timestamp <@ {0}.effective
            """).format(
                self.history_table_name,
                self.pk_column_name), dict(pk=self.pk))

        return cursor.fetchone().current_status

    def update_status(self, pgconn, new_status, who_did_it):

        qry = textwrap.dedent("""
            insert into {0}
            ({1}, status, who_did_it)
            values
            (%(pk)s, %(status)s, %(who_did_it)s)
            """.format(
                self.history_table_name,
                self.pk_column_name))

        cursor = pgconn.cursor()

        cursor.execute(qry,
            dict(
                pk=self.pk,
                status=new_status,
                who_did_it=who_did_it))

        log.info("Just updated status for {0} to {1}".format(self, new_status))
