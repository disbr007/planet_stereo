import argparse
import copy
import hashlib
import json
import glob
import os
import sys
from pathlib import Path
import pathlib
import platform
import re

import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon
from tqdm import tqdm

from logging_utils.logging_utils import create_logger

logger = create_logger(__name__, 'sh', 'INFO')

# Constants
windows = 'Windows'
linux = 'Linux'
# Keys in metadata file
k_location = 'location'
k_scenes_id = 'id'
k_order_id = 'order_id'
# New fields that are created
k_filename = 'filename'
k_relative_loc = 'rel_location'

def win2linux(path):
    lp = path.replace('V:', '/mnt').replace('\\', '/')

    return lp


def linux2win(path):
    wp = path.replace('/mnt', 'V:').replace('/', '\\')

    return wp


def type_parser(filepath):
    '''
    takes a file path (or dataframe) in and determines whether it is a dbf,
    excel, txt, csv (or df), ADD SUPPORT FOR SHP****
    '''
    if isinstance(filepath, pathlib.PurePath):
        fp = str(filepath)
    else:
        fp = copy.deepcopy(filepath)
    if type(fp) == str:
        ext = os.path.splitext(fp)[1]
        if ext == '.csv':
            with open(fp, 'r') as f:
                content = f.readlines()
                for row in content[0]:
                    if len(row) == 1:
                        file_type = 'id_only_txt'  # txt or csv with just ids
                    elif len(row) > 1:
                        file_type = 'csv'  # csv with columns
                    else:
                        logger.error('Error reading number of rows in csv.')
        elif ext == '.txt':
            file_type = 'id_only_txt'
        elif ext in ('.xls', '.xlsx'):
            file_type = 'excel'
        elif ext == '.dbf':
            file_type = 'dbf'
        elif ext == '.shp':
            file_type = 'shp'
        elif ext == '.geojson':
            file_type = 'geojson'
    elif isinstance(fp, (gpd.GeoDataFrame, pd.DataFrame)):
        file_type = 'df'
    else:
        logger.error('Unrecognized file type. Type: {}'.format(type(fp)))

    return file_type


def read_ids(ids_file, field=None, sep=None, stereo=False):
    '''Reads ids from a variety of file types. Can also read in stereo ids from applicable formats
    field: field name, irrelevant for text files, but will search for this name if ids_file is .dbf or .shp
    '''

    # Determine file type
    file_type = type_parser(ids_file)

    if file_type in ('dbf', 'df', 'gdf', 'shp', 'csv', 'excel', 'geojson') and not field:
        logger.error('Must provide field name with file type: {}'.format(file_type))
        sys.exit()

    # Text file
    if file_type == 'id_only_txt':
        ids = []
        with open(ids_file, 'r') as f:
            content = f.readlines()
            for line in content:
                if sep:
                    # Assumes id is first
                    the_id = line.split(sep)[0]
                    the_id = the_id.strip()
                else:
                    the_id = line.strip()
                ids.append(the_id)

    # csv
    elif file_type in ('csv'):
        df = pd.read_csv(ids_file, sep=sep, )
        ids = list(df[field])

    # dbf, gdf, dbf
    elif file_type in ('dbf'):
        df = gpd.read_file(ids_file)
        ids = list(df[field])

    # SHP
    elif file_type == 'shp':
        df = gpd.read_file(ids_file)
        ids = list(df[field])
    # GEOJSON
    elif file_type == 'geojson':
        df = gpd.read_file(ids_file, driver='GeoJSON')
        ids = list(df[field])
    # GDF, DF
    elif file_type in ('gdf', 'df'):
        ids = list(ids_file[field])

    # Excel
    elif file_type == 'excel':
        df = pd.read_excel(ids_file, squeeze=True)
        ids = list(df[field])

    else:
        logger.error('Unsupported file type... {}'.format(file_type))

    return ids


def remove_dt_gdf(gdf, date_format='%Y-%m-%d %H:%M:%S'):
    # Convert datetime columns to str
    date_cols = gdf.select_dtypes(include=['datetime64']).columns
    for dc in date_cols:
        gdf[dc] = gdf[dc].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))


def write_gdf(gdf, out_footprint, out_format=None, date_format=None):
    if not isinstance(out_footprint, pathlib.PurePath):
        out_footprint = Path(out_footprint)

    # Remove datetime - specifiy datetime if desired format
    if not gdf.select_dtypes(include=['datetime64']).columns.empty:
        remove_dt_gdf(gdf, date_format=date_format)
    logger.info('Writing to file: {}'.format(out_footprint))
    if not out_format:
        out_format = out_footprint.suffix.replace('.', '')
        if not out_format:
            # If still no extension, check if gpkg (package.gpkg/layer)
            out_format = out_footprint.parent.suffix
            if not out_format:
                logger.error('Could not recognize out format from file extension: {}'.format(out_footprint))

    # Write out in format specified
    if out_format == 'shp':
        gdf.to_file(out_footprint)
    elif out_format == 'geojson':
        gdf.to_file(out_footprint,
                    driver='GeoJSON')
    elif out_format == 'gpkg':
        gdf.to_file(out_footprint.parent, layer=out_footprint.stem,
                    driver='GPKG')
    else:
        logger.error('Unrecognized format: {}'.format(out_format))

    logger.debug('Writing complete.')


def parse_group_args(parser, group_name):
    # Get just arguments in given group from argparse.ArgumentParser() as Namespace object
    args = parser.parse_args()
    arg_groups = {}
    for group in parser._action_groups:
        group_dict = {a.dest: getattr(args, a.dest, None) for a in group._group_actions}
        arg_groups[group.title] = argparse.Namespace(**group_dict)
    parsed_attribute_args = arg_groups[group_name]

    return parsed_attribute_args


def get_platform_location(path):
    if platform.system() == 'Linux':
        pl = win2linux(path)
    elif platform.system() == 'Windows':
        pl = linux2win(path)

    return pl


def id_from_scene(scene, scene_levels=['1B', '3B']):
    """scene : pathlib.Path"""
    if not isinstance(scene, pathlib.PurePath):
        scene = Path(scene)
    scene_name = scene.stem
    scene_id = None
    for lvl in scene_levels:
        if lvl in scene_name:
            scene_id = scene_name.split('_{}_'.format(lvl))[0]
    if not scene_id:
        logger.error('Could not parse scene ID with any level '
                     'in {} from {}'.format(scene_levels, scene_name))

    return scene_id


def gdf_from_metadata(scene_md_paths, relative_directory=None,
                      relative_locs=False, pgc_locs=True,
                      rel_loc_style='W'):
    rows = []
    for sm in tqdm(scene_md_paths):
        # Get scene paths
        scene_path = sm[0]
        metadata_path = sm[1]

        logger.debug('Parsing metdata for: {}\{}'.format(scene_path.parent.stem,
                                                         scene_path.stem))
        metadata = json.load(open(metadata_path))
        properties = metadata['properties']

        # Create paths for both Windows and linux
        # Keep only Linux - Use windows for checking existence if code run on windows
        if platform.system() == windows:
            wl = str(scene_path)
            tn = win2linux(str(scene_path))
            if os.path.exists(wl):
                add_row = True
            else:
                add_row = False
        elif platform.system() == linux:
            tn = str(scene_path)
            # wl = linux2win(str(scene_path))
            if os.path.exists(tn):
                add_row = True
            else:
                add_row = False
        if pgc_locs:
            properties[k_location] = tn
        if relative_locs:
            rl = Path(scene_path).relative_to(Path(relative_directory))
            if rel_loc_style == 'W' and platform.system() == 'Linux':
                properties[k_relative_loc] = linux2win(str(rl))
            elif rel_loc_style == 'L' and platform.system() == 'Windows':
                properties[k_relative_loc] = win2linux(str(rl))
            else:
                properties[k_relative_loc] = str(rl)
            oid = Path(metadata_path).relative_to(relative_directory).parts[0]
        properties[k_scenes_id] = metadata['id']
        # properties[k_order_id] = oid
        properties[k_filename] = scene_path.name

        try:
            # TODO: Figure out why some footprints are multipolygon - handle better
            if metadata['geometry']['type'] == 'Polygon':
                properties['geometry'] = Polygon(metadata['geometry']['coordinates'][0])
            elif metadata['geometry']['type'] == 'MultiPolygon':
                logger.warning('Skipping MultiPolygon geometry')
                add_row = False
                # properties['geometry'] = MultiPolygon([Polygon(metadata['geometry']['coordinates'][i][0])
                #                                        for i in range(len(metadata['geometry']['coordinates']))])
        except Exception as e:
            logger.error('Geometry error, skipping add scene: {}'.format(properties[k_scenes_id]))
            logger.error('Metadata file: {}'.format(metadata_path))
            logger.error('Geometry: {}'.format(metadata['geometry']))
            logger.error(e)
            add_row = False

        if add_row:
            rows.append(properties)
        else:
            logger.warning('Scene could not be found (or had bad geometry), '
                           'skipping adding:\n{}\tat {}'.format(metadata['id'], scene_path))

    if len(rows) == 0:
        # TODO: Address how to actually deal with not finding any features - sys.exit()?
        logger.warning('No features to convert to GeoDataFrame.')

    gdf = gpd.GeoDataFrame(rows, geometry='geometry', crs='epsg:4326')

    return gdf


def metadata_path_from_scene(scene):
    par_dir = scene.parent
    sid = id_from_scene(scene)
    metadata_path = par_dir / '{}_metadata.json'.format(sid)

    return metadata_path


def find_scene_files(data_directory):
    # TODO: search for manifest.json files and use those to locate scenes
    # TODO: Pass in list of manifest files?
    scenes_to_parse = []
    for root, dirs, files in os.walk(data_directory):
        for f in files:
            # TODO: Improve identification of scene files
            if f.endswith('.tif') and not f.endswith('_udm.tif'):
                scene = Path(root) / f
                scenes_to_parse.append(scene)

    return scenes_to_parse


def find_scene_files(data_directory):
    """Locate scene files based on previously created scene level
    *_manifest.json files."""
    scene_files = []
    # Find all manifest files, using the underscore will prevent
    # master manifests from being found.
    all_manifests = Path(data_directory).rglob('*_manifest.json')
    for manifest in all_manifests:
        with open(str(manifest), 'r') as src:
            data = json.load(src)
            # Find the scene path within the manifest
            scene_path = data['path']
            scene_files.append(scene_path)

    return scene_files


def find_scene_meta_files(scene, req_meta=['manifest.json', 'metadata.xml']):
    # scene_meta_files = glob.glob("{}*".format(str(scene.parent / scene.stem)))
    scene_meta_files = [f for f in scene.parent.rglob('{}*'.format(scene.stem))]
    scene_meta_files.append(metadata_path_from_scene(scene))
    scene_meta_files = [Path(p) for p in scene_meta_files]

    print(scene_meta_files)
    # This looks for matches with each req_meta suffix in the list of scene_meta_files
    req_meta_matches = [list(filter(lambda x: re.match('.*{}'.format(s), str(x)), scene_meta_files)) for s in req_meta]
    req_meta_matches = [f for matchlist in req_meta_matches for f in matchlist]
    if len(req_meta_matches) != len(req_meta):
        print('Missing meta files')
    scene_meta_files.remove(scene)

    return scene_meta_files


def create_file_md5(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)

    return hash_md5.hexdigest()


def verify_scene_md5(manifest_md5, scene_file):
    file_md5 = create_file_md5(scene_file)
    if file_md5 == manifest_md5:
        verified = True
    else:
        logger.warning('Verification of md5 checksum failed: {} != {}'.format(file_md5, manifest_md5))
        verified = False

    return verified


class PlanetScene:
    """Write"""
    def __init__(self, manifest):
        self.manifest = Path(manifest)
        # Parse manifest for attributes
        with open(str(self.manifest), 'r') as src:
            data = json.load(src)
            # Find the scene path within the manifest
            _digests = data['digests']
            _annotations = data['annotations']
            self.scene_path = self.manifest.parent.parent / data['path']
            self.media_type = data['size']
            self.md5 = _digests['md5']
            self.sha256 = _digests['sha256']
            self.asset_type = _annotations['planet/asset_type']
            self.bundle_type = _annotations['planet/bundle_type']
            self.item_id = _annotations['planet/item_id']
            self.item_type = _annotations['planet/item_type']
        # Empty attributes calculated from methods
        self.valid_md5 = None

        # Bundle types that have been tested for compatibility with naming conventions
        self.supported_bundle_types = ['analytic', 'analytic_sr',
                                       'basic_analytic', 'basic_analytic_nitf',
                                       'basic_uncalibrated_dn', 'basic_uncalibrated_dn_ntif',
                                       'uncalibrated_dn']
        # Ensure bundle_type has been tested
        if self.bundle_type not in self.supported_bundle_types:
            logger.error('Bundle type not tested: {}'.format(self.bundle_type))

    def verify_checksum(self):
        self.valid_md5 = verify_scene_md5(self.md5, self.scene_path)

    def get_xml(self):
        # First n chars * _metadata.xml
        # Use bundle_type to determine filename
        pass

ps = PlanetScene(r'V:\pgc\data\scratch\jeff\projects\planet\data'
                 r'\00889167-0f83-441a-8122-481e45c01d54\PSScene4Band'
                 r'\20191009_160416_100d_1B_AnalyticMS_manifest.json')





