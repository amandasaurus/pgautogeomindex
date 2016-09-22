# pgautogeomindex

Automatically deduce what geometric indexes need to be added to your database,
based on your slow query log

When using a PostGIS database to render maps (e.g. for OpenStreetMap), it's
common to have queries like this:

    SELECT ST_AsBinary("way") AS geom,"access","bridge","render","stylegroup","tunnel","type" FROM ( SELECT way, COALESCE(highway, railway) AS type, 0 AS tunnel, 0 AS bridge, access, 'fill' AS render,  CASE    WHEN highway IN ('motorway', 'trunk') THEN 'motorway'    WHEN highway IN ('primary', 'secondary' ) THEN 'mainroad'    WHEN highway IN ('primary_link', 'secondary_link','tertiary', 'tertiary_link','residential', 'unclassified', 'road', 'living_street') THEN 'minorroad'   WHEN highway IN ('motorway_link') THEN 'motorway_link'   WHEN highway IN ('trunk_link') THEN 'trunk_link'    WHEN highway IN ('service', 'track') THEN 'service'    WHEN highway IN ('path', 'cycleway', 'footway', 'pedestrian', 'steps', 'bridleway')  OR railway IN ('platform') THEN 'noauto'    WHEN railway IN ('light_rail', 'subway', 'narrow_gauge', 'rail', 'tram') THEN 'railway'    ELSE 'other' END AS stylegroup  FROM planet_osm_line  WHERE ((highway IS NOT NULL  AND highway !='proposed' AND highway !='construction') OR (railway IS NOT NULL AND railway !='proposed' AND railway != 'construction' AND railway !='razed' AND railway !='abandoned') )    AND (tunnel IS NULL OR tunnel = 'no')    AND (bridge IS NULL OR bridge = 'no')      ORDER BY z_order) AS data WHERE "way" && ST_SetSRID('BOX3D(-1271912.150665333 6868325.613592795,-606604.2564711587 7533633.507786972)'::box3d, 900913)

If you only have a simple geometry index (on the `way` column), it can be slow.
Performance can be increased by creating a new index with on the geometry
column with a `WHERE` clause. pgautogeomindex will figure that out, and suggest
an index like this:

    CREATE INDEX planet_osm_line_idx19291080 ON planet_osm_line USING GIST (way) WHERE (((tunnel IS NULL) OR (tunnel = 'no'::text)) AND ((bridge IS NULL) OR (bridge = 'no'::text)) AND (((highway IS NOT NULL) AND (highway <> 'proposed'::text) AND (highway <> 'construction'::text)) OR ((railway IS NOT NULL) AND (railway <> 'proposed'::text) AND (railway <> 'construction'::text) AND (railway <> 'razed'::text) AND (railway <> 'abandoned'::text))));


## Usage

First run your rendering on your database to generate some slow queries in the
log.

    pgautogeomindex -i /path/to/slow/query.log

The output is the SQL queries to run. It needs to connect to the database to
perform `EXPLAIN` queries, specify the database with `-d`/`--database` and/or
the user to connect as with `-U`/`--user`.

### Options

    usage: pgautogeomindex [-h] [-d DATABASE] [-U USER] [-c GEOM_COLUMN] -i INPUT

    optional arguments:
      -h, --help            show this help message and exit
      -d DATABASE, --database DATABASE
                            PostgreSQL database name
      -U USER, --user USER  PostgreSQL database user
      -c GEOM_COLUMN, --geom-column GEOM_COLUMN
                            Geometry column name
      -i INPUT, --input INPUT
                            Slow query log


## Bugs

There may be bugs. I had to figure out what the fields in the `EXPLAIN` JSON
output was, and may have made mistakes. Bug reports are welcome.


## Copyright

Copyright 2016 Rory McCann <rory@technomancy.org>. Licenced under the GNU Affero GPL
v3 (or later). See the file `LICENCE` for more.
