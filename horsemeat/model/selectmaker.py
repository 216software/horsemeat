# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import logging
import textwrap

log = logging.getLogger(__name__)

class SelectMaker(object):

    """
    Just an experiment right now.

    >>> q = SelectMaker(['a', 'b'], 'foo')
    >>> print(q.qry) # doctest: +NORMALIZE_WHITESPACE
    select a, b
    from foo

    >>> q = SelectMaker(['a', 'b'], 'foo', [], ['a>99', 'b=11'])

    >>> print(q.qry) # doctest: +NORMALIZE_WHITESPACE
    select a, b
    from foo
    where a>99
    and b=11

    >>> q = SelectMaker(['foo.a', 'foo.b'], 'foo', [('join', 'bar', 'foo.a = bar.a')], ['a>99', 'b=11'])

    >>> print(q.join_tables_and_clauses)
    join bar on foo.a = bar.a

    >>> print(q.qry) # doctest: +NORMALIZE_WHITESPACE
    select foo.a, foo.b
    from foo
    join bar
    on foo.a = bar.a
    where a>99
    and b=11

    """

    def __init__(self, select_columns, from_table,
        join_tables_and_clauses=None, where_clauses=None):

        self.select_columns = select_columns
        self.from_table = from_table
        self.join_tables_and_clauses = join_tables_and_clauses
        self.where_clauses = where_clauses

    @property
    def join_tables_and_clauses(self):

        if self._join_tables_and_clauses:

            return '\n'.join([
                "{0} {1} on {2}".format(a, b, c)
                for (a, b, c) in self._join_tables_and_clauses])


    @join_tables_and_clauses.setter
    def join_tables_and_clauses(self, val):

        self._join_tables_and_clauses = val

    @property
    def select_columns(self):
        return ', '.join(self._select_columns)

    @select_columns.setter
    def select_columns(self, val):
        self._select_columns = val

    @property
    def qry(self):

        s = textwrap.dedent("""
            select {select_columns}
            from {from_table}
            """.format(
                select_columns=self.select_columns,
                from_table=self.from_table,
        ))

        if self.join_tables_and_clauses:
            s += self.join_tables_and_clauses

        if self.where_clauses:

            s += textwrap.dedent("""
                where {where_clauses}
                """.format(
                    where_clauses='\nand '.join(self.where_clauses)))
        return s

