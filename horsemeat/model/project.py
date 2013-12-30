# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import logging
import textwrap

from horsemeat.model import junkdrawer

class Project(object):

    def __init__(self, pgconn, project_id, owner_id):
        self.pgconn = pgconn
        self.project_id = project_id
        self.owner_id = owner_id

    def look_up_project_details(self):

        cursor = self.pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select project_id, title, description, owner_id
            from projects
            where project_id = (%s)
            and owner_id = (%s)
            """), [self.project_id, self.owner_id])

        if cursor.rowcount:
            return cursor.fetchone()

        else:
            raise ProjectNotFound(
                "Sorry, this account doesn't have a project {0}".format(
                    self.project_id))


    def look_up_everything(self):

        d = self.build_extra_segments_dictionary()

        return dict(
            details=self.look_up_project_details(),
            products=self.get_my_products(),

            industries=industry.get_all_industries_for_project(
                self.pgconn,
                self.project_id),

            issues=issue.get_all_issues_for_project(
                self.pgconn,
                self.project_id),

            trends=trend.get_all_trends_for_project(
                self.pgconn,
                self.project_id),

            competitors=competitor.get_all_competitors_for_project(
                self.pgconn,
                self.project_id),

            geographic_regions=geographic_region.get_all_geographic_regions_for_project(
                self.pgconn,
                self.project_id),

            goals=goal.get_all_goals_for_project(
                self.pgconn,
                self.project_id),

            benefits=self.get_my_benefits(),
            features=self.get_my_features(),
            needs=self.get_my_needs(),

            **d
        )

    def get_extra_segment_titles(self):

        qry = textwrap.dedent("""
            select extra_segment_1_title, extra_segment_2_title,
            extra_segment_3_title, extra_segment_4_title
            from extra_segment_titles
            where project_id = (%s)
            """)

        cursor = self.pgconn.cursor()

        cursor.execute(qry, [self.project_id])

        if cursor.rowcount:

            row = cursor.fetchone()

            return [
                row.extra_segment_1_title,
                row.extra_segment_2_title,
                row.extra_segment_3_title,
                row.extra_segment_4_title]

        else:
            return []

    def build_extra_segments_dictionary(self):

        d = dict(extra_segment_titles=self.get_extra_segment_titles())

        for i, t in enumerate(d['extra_segment_titles'], start=1):

            if t:
                d[t.lower().replace(' ', '_')] = self.get_extra_segment_data(i)

        return d


    def get_extra_segment_data(self, num):

        cursor = self.pgconn.cursor()

        pk_name = 'extra_segment_{0}_id'.format(num)
        table_name = 'extra_segment_{0}'.format(num)
        title_column_name = 'extra_segment_{0}_title'.format(num)

        qry = textwrap.dedent("""
            select b.{title_column_name} as segment_title, a.{pk_name},
            a.project_id, a.title, a.description,
            a.use_as_market_segment, a.inserted, a.updated, '{pk_name}'
            as pk_name

            from {table_name} a

            left join extra_segment_titles b
            on a.project_id = b.project_id

            where a.project_id = (%s)
            """.format(
                pk_name=pk_name,
                table_name=table_name,
                title_column_name=title_column_name))

        cursor.execute(qry, [self.project_id])

        return cursor


    def get_my_products(self):

        cursor = self.pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select product_id, title, description
            from products
            where project_id = (%s)
            order by title
        """), [self.project_id])

        return cursor

    def get_my_features(self):

        cursor = self.pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select feature_id, title, description,
            use_as_market_segment,
            'feature_id' as pk_name
            from features

             where project_id = (%s)
            order by title
        """), [self.project_id])

        return cursor

    def get_my_benefits(self):

        cursor = self.pgconn.cursor()

        cursor.execute(textwrap.dedent("""

            select b.benefit_id, b.title, b.description,
            b.use_as_market_segment,
            array_agg(f.feature_id) as features,
            array_agg(f.title) as feature_titles,
            'benefit_id' as pk_name
            from benefits as b
            left join feature_benefit_link as fbl
            on fbl.benefit_id = b.benefit_id
            left join features as f
            on f.feature_id = fbl.feature_id
            where b.project_id = (%s)
            group by b.benefit_id
            order by b.title

        """), [self.project_id])

        return cursor


    def get_my_needs(self):

        """

        Returns all of the needs in the database
        for a given project. Also creates an
        array of the linked benefits. If no benefits
        have been linked to the specific need, then
        we get a {NULL} array

        """

        cursor = self.pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select n.need_id, n.title, n.description,
            n.use_as_market_segment,
            array_agg(bnl.benefit_id) as benefits,
            array_agg(b.title) as benefit_titles,
            'need_id' as pk_name
            from needs as n
            left join benefit_need_link as bnl
            on bnl.need_id = n.need_id
            left join benefits as b
            on b.benefit_id = bnl.benefit_id
            where n.project_id = (%s)
            group by n.need_id
            order by n.title

        """), [self.project_id])

        return cursor



class ProjectNotFound(Exception):

    """
    When you give a project ID that isn't in the database, you get this.
    """

def verify_user_owns_project(pgconn, user_id, project_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select exists(
            select projects.project_id
            from projects
            where projects.owner_id = (%s)
            and projects.project_id = (%s)
        )"""),
        [user_id, project_id])

    return cursor.fetchone().exists

def look_up_project_details(pgconn, project_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select project_id, title, description, owner_id
        from projects
        where project_id = (%s)
        """), [project_id])

    if cursor.rowcount:
        return cursor.fetchone()

def clear_all_market_segments(pgconn, project_id):

    """
    Don't get this confused with the delete_market_segments!  They work
    on different tables.
    """

    for table_name in junkdrawer.market_segment_tables:

        cursor = pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            update {0}
            set use_as_market_segment = false
            where project_id = (%s)
            """.format(table_name)),
            [project_id])


def delete_market_segments(pgconn, project_id):

    """
    Bad naming!  This delete method deletes all the rows in the market_segments
    table.
    """

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        delete from market_segments
        where project_id = (%s)
        """),
        [project_id])


def build_completion_dictionary(pgconn, project_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select task_url, current_status
        from project_completion
        where project_id = (%s)
        """), [project_id])

    d = dict()

    status_to_html_stuff = dict({
        'not started': ['color: inherit;', 'icon-check-empty'],
        'in progress': ['color: inherit;', 'icon-check-empty'],
        'finished': ['color: green;', 'icon-check'],
    })

    for task_url, current_status in cursor:
        d[task_url] = status_to_html_stuff[current_status]

    return d

