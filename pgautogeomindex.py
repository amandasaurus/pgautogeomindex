import psycopg2, json
from pprint import pprint
import argparse
import sys
import re

def rm_geom_condition(geom_column, filter):
    # There are many places the geom filter could be.
    # Either "X AND geom && BBOX AND Y", which needs to become "X AND Y"
    # "geom && BBOX AND Y" -> "Y"
    # "X AND geom && BBOX" -> "X"
    # "geom && BBOX" -> ""
    # _st_distance(geom, WKB) op number ( distance queries)
    # So we do a series of replacements, which should catch all cases, and not
    # overlap, only one of each one should work on each input string, we need
    # to include all 4 to ensure all 4 cases are covered
    new_filter = re.sub(" AND \({} && '[0-9A-F]+'::geometry\) AND ".format(geom_column), " AND ", filter)
    new_filter = re.sub("\({} && '[0-9A-F]+'::geometry\) AND ".format(geom_column), "", new_filter)
    new_filter = re.sub(" AND \({} && '[0-9A-F]+'::geometry\)".format(geom_column), "", new_filter)

    new_filter = re.sub("\({} && '[0-9A-F]+'::geometry\)".format(geom_column), "", new_filter)
    new_filter = re.sub("\(st_boundary\({}\) && '[0-9A-F]+'::geometry\)".format(geom_column), "", new_filter)

    new_filter = re.sub("AND \(_st_distance\(\({col}\)::geography, '[0-9A-F]+'::(geometry|geography), '[0-9]+'::double precision, true\) < '[0-9]+'::double precision\)".format(col=geom_column), "", new_filter)
    new_filter = new_filter.strip()
    return new_filter


def get_filters_from_plan(plan, geom_column):
    results = []

    if plan['Node Type'] == 'Seq Scan':
        filter = rm_geom_condition(geom_column, plan.get('Filter', ''))
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
    elif plan['Node Type'] in ('Values Scan',):
        # ignore this it's just going over a (VALUES (...)) thing
        pass
    elif 'Plans' in plan:
        for sub_plan in plan['Plans']:
            results.extend(get_filters_from_plan(sub_plan, geom_column))

    else:
        raise NotImplementedError(plan)
    
    # TODO remove the geom column filter

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--database', type=str, help="PostgreSQL database name", default="gis")
    parser.add_argument('-U', '--user', type=str, required=False, help="PostgreSQL database user")

    parser.add_argument('--analyze', action="store_true", help="Include ANALYZE statements afterwards (default)")
    parser.add_argument('--no-analyze', action="store_false", dest="analyze", help="Don't include ANALYZE statements afterwards")

    parser.add_argument('--include-if-not-exists', action="store_true", default=True, help="Include IF NOT EXISTS clause on index creation (default)")
    parser.add_argument('--no-include-if-not-exists', action="store_false", dest="include_if_not_exists", help="Don't include IF NOT EXISTS clause")

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

    # Store the list of pg_catalog tables
    cursor.execute("select table_name from information_schema.tables where table_schema = 'pg_catalog';")
    pg_catalog_tables = set([x[0] for x in cursor.fetchall()])

    # read in input
    if args.input:
        with open(args.input) as fp:
            log_file = fp.read()

    geom_column = args.geom_column
    tables_to_analyze = set()
    queries = set()

    log_regex = re.compile(r"""(\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d\d\d) .{,6} \[[^\]]{,20}\] \w{,10}@\w{,10} (?:LOG:  (?:duration: [0-9]{,15}\.[0-9]{,6} ms  (?:execute <\w{,10}>|statement):)?|ERROR|STATEMENT))""", re.DOTALL)

    splits = log_regex.split(log_file)

    splits = splits[1:]   # empty one at start

    splits = [(splits[i], splits[i+1]) for i in range(0, len(splits), 2)]  # group
    for header, sql in splits:
        if "duration" not in header:
            continue
        if "LOG: " not in header:
            continue

        if any(sql.strip().upper().startswith(ignore) for ignore in ['BEGIN', 'ALTER ', 'SET ', 'ERROR ']):
            continue

        try:
            new_sql = "EXPLAIN (FORMAT JSON) {};".format(sql)
            cursor.execute(new_sql)
            res = cursor.fetchone()[0][0]['Plan']

            for (filter, table_name) in get_filters_from_plan(res, geom_column):
                if table_name in pg_catalog_tables:
                    continue
                tables_to_analyze.add(table_name)
                idx_suffix = str(abs(hash(filter)))[:8]
                if_not_exists = " IF NOT EXISTS" if args.include_if_not_exists else ""
                add_index_query = "CREATE INDEX{if_not_exists} {table}_idx{suffix} ON {table} USING GIST ({geom}) WHERE {filter};".format(table=table_name, suffix=idx_suffix, filter=filter, geom=geom_column, if_not_exists=if_nt_exists)
                queries.add(add_index_query)

        except Exception as e:
            print sql
            print repr(e)

    queries = sorted(queries)
    for query in queries:
        print query

    if args.analyze:
        for table_name in sorted(tables_to_analyze):
            print "ANALYZE {};".format(table_name)



if __name__ == '__main__':
    main()


