import psycopg2, json
from pprint import pprint
import argparse
import sys
import re

def rm_geom_condition(geom_column, filter):
    # There are many places the geom filter could be.
    # Either "X AND geom && blah AND Y", which needs to become "X AND Y"
    # "geom && blah AND Y" -> "Y"
    # "X AND geom && blah" -> "X"
    # "geom && blah" -> ""
    # So we do a series of replacements, which should catch all cases, and not
    # overlap, only one of each one should work on each input string, we need
    # to include all 4 to ensure all 4 cases are covered
    new_filter = re.sub(" AND \({} && '[0-9A-F]+'::geometry\) AND ".format(geom_column), " AND ", filter)
    new_filter = re.sub("\({} && '[0-9A-F]+'::geometry\) AND ".format(geom_column), "", new_filter)
    new_filter = re.sub(" AND \({} && '[0-9A-F]+'::geometry\)".format(geom_column), "", new_filter)

    new_filter = re.sub("\({} && '[0-9A-F]+'::geometry\)".format(geom_column), "", new_filter)
    new_filter = new_filter.strip()
    return new_filter


def get_filters_from_plan(plan, geom_column):
    results = []
    if plan['Node Type'] == 'Seq Scan':
        filter = rm_geom_condition(geom_column, plan['Filter'])
        if filter != '':
            table = plan['Relation Name']
            results.append((filter, table))
    elif plan['Node Type'] == 'Index Scan':
        filter = rm_geom_condition(geom_column, plan.get('Filter', ""))
        if filter != '':
            table = plan['Relation Name']
            results.append((filter, table))
    elif plan['Node Type'] in ('Bitmap Index Scan', 'Bitmap Heap Scan'):
        filter = rm_geom_condition(geom_column, plan['Recheck Cond'])
        if filter != '':
            table = plan['Relation Name']
            results.append((filter, table))
    elif 'Plans' in plan:
        for sub_plan in plan['Plans']:
            results.extend(get_filters_from_plan(sub_plan, geom_column))

    else:
        raise NotImplementedError
    
    # TODO remove the geom column filter


    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--database', type=str, help="PostgreSQL database name", default="gis")
    parser.add_argument('-U', '--user', type=str, required=False, help="PostgreSQL database user")

    parser.add_argument('-c', '--geom-column', type=str, required=False, help="Geometry column name", default="way")
    parser.add_argument('-i', '--input', metavar="FILENAME", type=str, required=True, help="Slow query log")

    args = parser.parse_args()

    connect_args = {}
    if args.database is not None:
        connect_args['database'] = args.database
    if args.user is not None:
        connect_args['user'] = args.user

    conn = psycopg2.connect(**connect_args)
    cursor = conn.cursor()

    # read in input
    if args.input:
        input_fp = open(args.input)

    slow_query_log = (x for x in input_fp if " duration: " in x)
    split = ( re.split(" duration: [0-9]+\.[0-9]+ ms  execute <unnamed>: ", x, maxsplit=1) for x in slow_query_log)
    queries = (x[1] for x in split if len(x) == 2)

    geom_column = args.geom_column
    tables_to_analyze = set()
    added_queries = set()

    for sql in queries:
        try:

            new_sql = "EXPLAIN (FORMAT JSON) {};".format(sql)
            cursor.execute(new_sql)
            res = cursor.fetchone()[0][0]['Plan']
            #pprint(res)

            for (filter, table_name) in get_filters_from_plan(res, geom_column):
                tables_to_analyze.add(table_name)
                idx_suffix = str(abs(hash(filter)))[:8]
                add_index_query = "CREATE INDEX {table}_idx{suffix} ON {table} USING GIST ({geom}) WHERE {filter};".format(table=table_name, suffix=idx_suffix, filter=filter, geom=geom_column)
                if add_index_query not in added_queries:
                    print add_index_query
                    added_queries.add(add_index_query)

        except Exception as e:
            print repr(e)

    for table_name in tables_to_analyze:
        print "ANALYZE {};".format(table_name)



if __name__ == '__main__':
    main()


