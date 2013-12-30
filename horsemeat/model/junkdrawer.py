# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

"""
Stuff that needs to be better organized starts off being in here
"""

pk_names = dict({

    'industry_id': dict({
        'table_name': 'industries',
        'pretty_name': 'Industries',
        'singular_name': 'Industry',
    }),

    'application_id': dict({
        'table_name': 'applications',
        'pretty_name': 'Applications',
    }),

    'issue_id': dict({
        'table_name': 'issues',
        'pretty_name': 'Issues',
    }),

    'trend_id': dict({
        'table_name': 'trends',
        'pretty_name': 'Trends',
    }),

    'competitor_id': dict({
        'table_name': 'competitors',
        'pretty_name': 'Competition',
    }),

    'gr_id': dict({
        'table_name': 'geographic_regions',
        'pretty_name': 'Geographic Regions',
        'singular_name': 'Geographic Region',
    }),

    'brand_id': dict({
        'table_name': 'brands',
        'pretty_name': 'Brands',
    }),

    'goal_id': dict({
        'table_name': 'goals',
        'pretty_name': 'Goals',
    }),

    'feature_id': dict({
        'table_name': 'features',
        'pretty_name': 'Features',
    }),

    'benefit_id': dict({
        'table_name': 'benefits',
        'pretty_name': 'Benefits',
    }),

    'need_id': dict({
        'table_name': 'needs',
        'pretty_name': 'Needs',
    }),

    'extra_segment_1_id': dict({
        'table_name': 'extra_segment_1',
        'pretty_name': 'extra_segment_1',
    }),

    'extra_segment_2_id': dict({
        'table_name': 'extra_segment_2',
        'pretty_name': 'extra_segment_2',
    }),

    'extra_segment_3_id': dict({
        'table_name': 'extra_segment_3',
        'pretty_name': 'extra_segment_3',
    }),

    'extra_segment_4_id': dict({
        'table_name': 'extra_segment_4',
        'pretty_name': 'extra_segment_4',
    }),

})

market_segment_tables = [
    'industries',
#     'applications',
    'issues',
    'trends',
    'competitors',
    'geographic_regions',
#     'brands',
    'goals',
    'features',
    'benefits',
    'needs',
    'extra_segment_1',
    'extra_segment_2',
    'extra_segment_3',
    'extra_segment_4',
]
