# coding: utf-8
import argparse
import logging
from pathlib import Path
import os
import psycopg2

from boltons.iterutils import remap
from ruamel.yaml import YAML

yaml = YAML()


def clean(base_path):
    import_directory = os.path.join(base_path, "imports", "debian-med")
    biotools_directory = os.path.join(base_path, "data")
    os.makedirs(import_directory, exist_ok=True)
    for data_file in Path(import_directory).glob("*.debian.yaml"):
        os.remove(data_file)
    for data_file in Path(biotools_directory).glob("*/*.debian.yaml"):
        os.remove(data_file)


def process_data(base_path):
    """Query UDD for debian-med packages and write them to YAML files in `import/debian-med`, plus in `data` if a biotools cross-link exists."""
    import_directory = os.path.join(base_path, "imports", "debian-med")
    biotools_directory = os.path.join(base_path, "data")
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.INFO)
    fileHandler = logging.FileHandler("debian_import.log")
    rootLogger.addHandler(fileHandler)
    consoleHandler = logging.StreamHandler()
    rootLogger.addHandler(consoleHandler)
    rootLogger.info("starting debian med metadata import from UDD...")
    connection = psycopg2.connect(
        user="udd-mirror",
        password="udd-mirror",
        host="udd-mirror.debian.net",
        port="5432",
        database="udd",
    )
    connection.set_client_encoding("UTF8")
    cursor = connection.cursor()
    query = """
    SELECT array_to_json(array_agg(t)) FROM (
        SELECT DISTINCT
            p.package, p.distribution, p.release, p.component,
            regexp_replace(regexp_replace(regexp_replace(regexp_replace(p.version, '-[.\d]+$', ''), '\+dfsg.*$', '') , '\+lgpl.*$', ''), '-\d*biolinux\d*$', '') AS version, 
            p.source, p.homepage, p.license as license, p.blend as blend, p.description_md5,
            edam.topics  as topics,
            edam.scopes  as edam_scopes
        FROM (
            SELECT * FROM (
            SELECT DISTINCT
                package, distribution, release, component, strip_binary_upload(version) AS version,
                source, homepage, description, description_md5, 'unknown' as license, 'debian-med' as blend
            FROM packages
            WHERE package IN
                            (SELECT DISTINCT package FROM blends_dependencies WHERE blend = 'debian-med')
            UNION
            SELECT DISTINCT
                package, 'prospective' AS distribution, 'vcs' AS release, component, strip_binary_upload(chlog_version) AS version,
                source, homepage, description, description_md5, license, blend
            FROM blends_prospectivepackages
            WHERE package IN
                            (SELECT DISTINCT package FROM blends_dependencies WHERE blend = 'debian-med')
        ) AS tmp
        ) AS p
        JOIN (
        -- select packages which have versions outside experimental
        SELECT px.package, strip_binary_upload(px.version) AS version,
                (SELECT release FROM ( SELECT release, sort FROM releases
                                        UNION
                                        SELECT 'vcs' AS release, 10000 AS sort
                                    ) reltmp WHERE sort = MAX(rx.sort)) AS release
            FROM (
            -- select highest version which is not in experimental - except if a package resides in experimental only
            SELECT pex.package, CASE WHEN pnoex.version IS NOT NULL THEN pnoex.version ELSE pex.version END AS version FROM
                (SELECT package, MAX(version) AS version FROM packages
                    WHERE package IN
                        (SELECT DISTINCT package FROM blends_dependencies WHERE blend = 'debian-med')
                    GROUP BY package
                ) pex
                LEFT OUTER JOIN
                (SELECT package, MAX(version) AS version FROM packages
                    WHERE package IN
                        (SELECT DISTINCT package FROM blends_dependencies WHERE blend = 'debian-med')
                        AND release != 'experimental'
                    GROUP BY package
                ) pnoex ON pex.package = pnoex.package
            UNION
            SELECT DISTINCT package, strip_binary_upload(chlog_version) AS version FROM blends_prospectivepackages
            ) px
            JOIN (
            -- select the release in which this version is available
            SELECT DISTINCT package, version, release FROM packages
                WHERE package IN
                        (SELECT DISTINCT package FROM blends_dependencies WHERE blend = 'debian-med')
            UNION
            SELECT DISTINCT package, chlog_version AS version, 'vcs' AS release FROM blends_prospectivepackages
                WHERE package IN
                        (SELECT DISTINCT package FROM blends_dependencies WHERE blend = 'debian-med')
            ) py ON px.package = py.package AND px.version = py.version
            JOIN ( SELECT release, sort FROM releases
                UNION 
                SELECT 'vcs' AS release, 10000 AS sort
                ) rx ON py.release = rx.release
            GROUP BY px.package, px.version
        ) AS pvar ON pvar.package = p.package AND pvar.version = p.version AND pvar.release = p.release
        LEFT OUTER JOIN edam   edam        ON p.source = edam.source       AND p.package = edam.package
    ORDER BY source, package
    ) t;
    """
    cursor.execute(query)
    data = cursor.fetchone()[0]
    cursor.close()
    cursor_loop = connection.cursor()
    for item in data:
        package_source = item["source"]
        package = item["package"]
        release = item["release"]
        description_md5 = item["description_md5"]
        rootLogger.info(f"processing package {package}")
        query_registries = f"select array_to_json(array_agg(t)) from (select entry, name from registry where source = '{package_source}') t"
        cursor_loop.execute(query_registries)
        registries_data = cursor_loop.fetchone()[0]
        item["registries"] = registries_data
        biotools = next(
            iter(
                [
                    ref.get("entry")
                    for ref in item.get("registries", []) or []
                    if ref.get("name") == "bio.tools"
                ]
            ),
            None,
        )
        biotools_xref = True
        if package == package_source:
            if biotools is None:
                rootLogger.warning(f"package '{package_source}' has no bio.tools ref.")
                biotools_xref = False
            else:
                biotools_package_directory = os.path.join(
                    biotools_directory, biotools.lower()
                )
                p = Path(biotools_package_directory)
                if not p.is_dir():
                    rootLogger.warning(
                        f"package '{package_source}' has a biotools ref ('{biotools}') but no folder exists."
                    )
                    biotools_xref = False
        else:
            rootLogger.warning(
                f"package name '{package}' is different from package source name '{package_source}', skipping."
            )
            biotools_xref = False
        rootLogger.info(
            f"processing package '{package_source} (known as {package} in debian)' with {'biotools ref ' + biotools if biotools_xref else 'with no biotools ref'}."
        )
        query_bib = f"select array_to_json(array_agg(t)) from (select key, package, rank, value from bibref where key = 'doi' AND source = '{package_source}') t"
        cursor_loop.execute(query_bib)
        bibref_data = cursor_loop.fetchone()[0]
        item["bib"] = bibref_data
        query_tags = f"select array_to_json(array_agg(t)) from (select tag from debtags where package='{package}') t"
        cursor_loop.execute(query_tags)
        tags_data = cursor_loop.fetchone()[0]
        item["tags"] = tags_data
        query_popcon = f"select array_to_json(array_agg(t)) from (select insts, nofiles, olde, recent, vote from popcon where package='{package}') t"
        cursor_loop.execute(query_popcon)
        popcon_data = cursor_loop.fetchone()[0]
        item["popcon"] = popcon_data
        query_descr = f"""select array_to_json(array_agg(t)) from (select package, description, long_description, language, release, description_md5, 'unknown' as license, 'debian-med' as blend
                      from descriptions
                      WHERE package IN
                      (SELECT DISTINCT package FROM blends_dependencies WHERE blend = 'debian-med') and package='{package}' and release='{release}' and (description_md5='{description_md5}' or description_md5 is null)
                      """
        if item["release"] == "vcs":
            query_descr += f"""
                      UNION
                      SELECT package, description, long_description, '', 'vcs' AS release, description_md5, license, blend FROM blends_prospectivepackages
                       where package='{package}' and (description_md5='{description_md5}' or description_md5 is null)"""
        query_descr += ") t"
        cursor_loop.execute(query_descr)
        descr_data = cursor_loop.fetchone()[0]
        item["descr"] = descr_data

        def drop_false(path, key, value):
            return bool(value)

        item = remap(item, visit=drop_false)
        file_path = os.path.join(import_directory, f"{item['package']}.debian.yaml")
        with open(file_path, "w") as fh:
            yaml.dump(item, fh)
        if biotools_xref:
            file_path = os.path.join(
                biotools_package_directory, f"{item['package']}.debian.yaml"
            )
            with open(file_path, "w") as fh:
                yaml.dump(item, fh)
    cursor_loop.close()
    connection.close()
    rootLogger.info("finished debian med metadata import from UDD.")


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", help="path to the output dir")
    return parser


def main():
    parser = get_parser()
    args = parser.parse_args()
    clean(args.output_dir)
    process_data(args.output_dir)


if __name__ == "__main__":
    main()
