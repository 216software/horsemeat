# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import collections
import logging
import textwrap

class ProductQueryMaker(object):

    def __init__(self, pgconn, product_id):
        self.pgconn = pgconn
        self.product_id = product_id

    def look_up_product_data(self):

        cursor = self.pgconn.cursor()

        sql = textwrap.dedent("""
            select p.product_id, p.project_id, p.title, p.description,
            p.age_in_years, p.age_in_years_extra_notes,
            p.revenue_level, p.revenue_level_extra_notes,
            p.profitability,
            p.profitability_extra_notes,
            p.expected_growth,
            p.expected_growth_extra_notes,
            p.is_a_missing_product,
            proj.title as project_title

            from products p

            join projects proj
            on p.project_id = proj.project_id

            where p.product_id = (%s)
            """)

        cursor.execute(sql, [self.product_id])

        return cursor.fetchone()

    def get_my_industries(self):

        cursor = self.pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select i.industry_id, i.title,
            i.description,
            exists(
                select * from
                product_industry_link pil
                where p.product_id = pil.product_id
                and i.industry_id = pil.industry_id
            ) as linked,

            pxl.extra_notes

            from products p
            join industries i
            on p.project_id = i.project_id

            left join product_industry_link pxl
            on p.product_id  = pxl.product_id
            and i.industry_id = pxl.industry_id

            where p.product_id = (%s)

            order by i.title
            """),
            [self.product_id])

        return cursor


    def get_my_trends(self):

        cursor = self.pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select x.trend_id, x.title,
            x.description,
            x.trend_type_title,

            exists(
                select * from
                product_trend_link pxl
                where p.product_id = pxl.product_id
                and x.trend_id = pxl.trend_id
            ) as linked,

            pxl.extra_notes

            from products p

            join trends x
            on p.project_id = x.project_id

            left join product_trend_link pxl
            on p.product_id  = pxl.product_id
            and x.trend_id = pxl.trend_id

            where p.product_id = (%s)

            order by x.title

            """),
            [self.product_id])

        return cursor

    """
    All trend types defined
    """
    def get_my_trend_types(self):

        cursor = self.pgconn.cursor()

        cursor.execute(textwrap.dedent("""

            select trend_type_title as title
            from trend_types

            order by trend_type_title

            """))

        return cursor

    def get_my_issues(self):

        cursor = self.pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select x.issue_id, x.title,
            x.description,
            exists(
                select * from
                product_issue_link pxl
                where p.product_id = pxl.product_id
                and x.issue_id = pxl.issue_id
            ) as linked,
            pxl.extra_notes

            from products p
            join issues x
            on p.project_id = x.project_id

            left join product_issue_link pxl
            on p.product_id  = pxl.product_id
            and x.issue_id = pxl.issue_id

            where p.product_id = (%s)

            order by x.title
            """),
            [self.product_id])

        return cursor

    def get_my_competitors(self):

        cursor = self.pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select x.competitor_id, x.title,
            x.description,
            exists(
                select * from
                product_competitor_link pxl
                where p.product_id = pxl.product_id
                and x.competitor_id = pxl.competitor_id
            ) as linked,
            pxl.extra_notes

            from products p join
            competitors x
            on p.project_id = x.project_id

            left join product_competitor_link pxl
            on p.product_id  = pxl.product_id
            and x.competitor_id = pxl.competitor_id

            where p.product_id = (%s)

            order by x.title
            """),
            [self.product_id])

        return cursor


    def get_my_geographic_regions(self):

        cursor = self.pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select x.gr_id, x.title,
            x.description,
            x.expected_growth,

            exists(
                select * from
                product_geographic_region_link pxl
                where p.product_id = pxl.product_id
                and x.gr_id = pxl.gr_id
            ) as linked,

            pxl.extra_notes,
            pxl.percent_of_total_product_sales

            from products p

            join geographic_regions x
            on p.project_id = x.project_id

            left join product_geographic_region_link pxl
            on p.product_id  = pxl.product_id
            and x.gr_id = pxl.gr_id

            where p.product_id = (%s)

            order by x.title
           """),
            [self.product_id])

        return cursor

    def get_my_goals(self):

        cursor = self.pgconn.cursor()

        cursor.execute(textwrap.dedent("""
            select x.goal_id, x.title,
            x.description,
            exists(
                select * from
                product_goal_link pxl
                where p.product_id = pxl.product_id
                and x.goal_id = pxl.goal_id
            ) as linked,
            pxl.extra_notes

            from products p

            join goals x
            on p.project_id = x.project_id

            left join product_goal_link pxl
            on p.product_id  = pxl.product_id
            and x.goal_id = pxl.goal_id

            where p.product_id = (%s)

            order by x.title
            """),
            [self.product_id])

        return cursor

def verify_user_owns_product(pgconn, user_id, product_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select exists(
            select products.product_id
            from products
            join projects
            on products.project_id = projects.project_id
            where projects.owner_id = (%s)
            and products.product_id = (%s)
        )"""),
        [user_id, product_id])

    return cursor.fetchone().exists

def get_products_in_project(pgconn, project_id):

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select product_id, title, description, age_in_years,
        age_in_years_extra_notes, revenue_level,
        revenue_level_extra_notes, profitability,
        profitability_extra_notes, expected_growth,
        expected_growth_extra_notes, product_gaps, num_skus,
        parent_product_id

        from products

        where project_id = (%s)

        order by title
        """), [project_id])

    return cursor

def build_product_trends_dictionary(pgconn, project_id):

    """
    Return a dictionary that maps product_id to a list of linked product
    trends.

    """

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select p.product_id, pt.title

        from product_trends pt

        join product_product_trend_link pptl
        on pt.product_trend_id = pptl.product_trend_id

        join products p
        on pptl.product_id = p.product_id

        where pt.project_id = (%(project_id)s)
        and p.project_id = (%(project_id)s)
        """), {'project_id':project_id})

    d = collections.defaultdict(list)

    for product_id, title in cursor:

        d[product_id].append(title)

    return d

def build_product_issues_dictionary(pgconn, project_id):

    """
    Return a dictionary that maps product_id to a list of linked product
    issues.

    """

    cursor = pgconn.cursor()

    cursor.execute(textwrap.dedent("""
        select p.product_id, pi.title

        from product_issues pi

        join product_product_issue_link ppil
        on pi.product_issue_id = ppil.product_issue_id

        join products p
        on ppil.product_id = p.product_id

        where pi.project_id = (%(project_id)s)
        and p.project_id = (%(project_id)s)
        """), {'project_id':project_id})

    d = collections.defaultdict(list)

    for product_id, title in cursor:

        d[product_id].append(title)

    return d

def look_up_product(pgconn, product_id):

    cursor = pgconn.cursor()

    sql = textwrap.dedent("""
        select p.product_id, p.project_id, p.title, p.description,
        p.age_in_years, p.age_in_years_extra_notes,
        p.revenue_level, p.revenue_level_extra_notes,
        p.profitability,
        p.profitability_extra_notes,
        p.expected_growth,
        p.expected_growth_extra_notes,
        p.is_a_missing_product,
        proj.title as project_title,
        p.product_gaps,
        p.product_overlaps,
        p.num_skus,
        p.parent_product_id

        from products p

        join projects proj
        on p.project_id = proj.project_id

        where p.product_id = (%s)
        """)

    cursor.execute(sql, [product_id])

    return cursor.fetchone()
