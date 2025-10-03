#!/usr/bin/env python3
import argparse
import xmlrpc.client

import os
import json

import datetime
import time
from pathlib import Path

import logging


logger = logging.getLogger('Sync')

class Phone:
    def __init__(self, url):
        self.url = url
        self.client = xmlrpc.client.ServerProxy(url, allow_none=True)

    def __getattr__(self, name, **kwargs):
        if hasattr(self.client, name):
            return getattr(self.client, name, **kwargs)

class Storage:
    def __init__(self, dir, path, metadata_path):
        self.dir = dir
        self.path = path
        self.metadata_path = metadata_path

    @staticmethod
    def metadata_for_path(asset):
        import copy
        z = copy.copy(asset)
        formats = ("Y", "m")
        for (suffix, key) in (("create", "creation_date"), ("mod", "modification_date")):
            t = asset[key]
            for f in formats:
                z[f + "_" + suffix] = datetime.datetime.utcfromtimestamp(t).strftime('%'+f)
        return z

    def get_path(self, asset):
        m = self.metadata_for_path(asset)
        return os.path.join(self.dir, self.path.format(**m))

    def get_metadata_path(self, asset):
        m = self.metadata_for_path(asset)
        p = Path(os.path.join(self.dir, self.metadata_path.format(**m)))
        return p.with_suffix('.json')

    def files_to_sync(self, on_phone):
        to_sync = []
        for asset in on_phone:
            path_to_metadata = self.get_metadata_path(asset)
            if not os.path.isfile(path_to_metadata):
                logger.debug(f'Syncing {asset["local_id"]} because missing.')
                to_sync.append(asset)
                continue

            # The file exists, check if modified date is the same.
            with open(path_to_metadata) as f:
                data = json.load(f)

            if data["modification_date"] != asset["modification_date"]:
                logger.debug(f'Syncing {asset["local_id"]} modification_date differs.')
                to_sync.append(asset)
                continue

            # nothing to do!
            logger.debug(f'Skipping {asset["local_id"]} already got it.')
        return to_sync

    def load_from_disk(self, asset):
        path_to_metadata = self.get_metadata_path(asset)
        with open(path_to_metadata) as f:
            data = json.load(f)

        # We got the metadata, now add the filesize and md5sum.
        get_path = self.get_path(asset)
        # Read it back to obtain the md5.
        with open(get_path, "rb") as f:
            z = f.read()

        # calculate the hash.
        import hashlib
        m = hashlib.md5()
        m.update(z)
        h = m.hexdigest()

        data["_filesize"] = len(z)
        data["_md5"] = h
        return data
        

    def retrieve(self, p, asset):
        get_path = self.get_path(asset)
        path_to_metadata = self.get_metadata_path(asset)
        logger.debug(f'Retrieving id: {asset["local_id"]} modified at {asset["modification_date"]}')
        retrieved = p.retrieve_asset_by_local_id(asset["local_id"])
        logger.debug(f'  Retrieved {len(retrieved["_data"].data)} bytes')

        # Ensure directories exist.
        os.makedirs(os.path.dirname(get_path), exist_ok=True)
        os.makedirs(os.path.dirname(path_to_metadata), exist_ok=True)

        # Next, write the actual data.
        with open(get_path, "wb") as f:
            f.write(retrieved["_data"].data)

        # Read it back to obtain the md5.
        with open(get_path, "rb") as f:
            z = f.read()


        logger.debug(f'  Data size: {len(z)}')
        logger.debug(f'  _filesize: {retrieved["_filesize"]}')

        if len(z) != retrieved["_filesize"]:
            raise BaseException(f"File size incorrect for {get_path}, expected {len(z)}.")

        import hashlib
        m = hashlib.md5()
        m.update(z)
        h = m.hexdigest()
        expected = retrieved["_md5"]

        logger.debug(f'   md5: {h}')
        logger.debug(f'  _md5: {retrieved["_md5"]}')

        if h != expected:
            raise BaseException(f"Md5 does not match! Got {h} for {get_path}, expected {expected}")

        # we got here, file retrieved correctly, write the metadata
        clean_metadata = {k:v for k, v in retrieved.items() if not k.startswith("_")}

        
        logger.debug(f'  Writing metadata.')
        with open(path_to_metadata, "w") as f:
            json.dump(clean_metadata, f)

        return retrieved

def run_sync(args):
    logger.info(f'Running sync.')
    logger.debug(f' host: {args.host}')
    logger.debug(f' dir: {args.dir}')
    logger.debug(f' path: {args.path}')
    logger.debug(f' metadata_path: {args.metadata_path}')

    p = Phone(args.host)
    sync = Storage(dir=args.dir, path=args.path, metadata_path=args.metadata_path)
    on_phone = p.get_all_metadata()

    logger.info(f"On phone: {len(on_phone)}")
    to_sync = sync.files_to_sync(on_phone)
    logger.info(f"To sync : {len(to_sync)}")
    total = len(to_sync)
    for i, asset in enumerate(to_sync):
        retrieved = sync.retrieve(p, asset)
        filename = retrieved["filename"]
        size = retrieved["_filesize"]
        date =  datetime.datetime.utcfromtimestamp(retrieved["creation_date"]).strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"{i+1: >5} / {total: >5}: {filename: >20} {date} ({size: >9} bytes)")

def run_test(args):
    p = Phone(args.host)
    print(p.client.get_asset_collections())
    metadata = p.client.get_all_metadata()
    
    img = [f for f in metadata if f["media_type"] == "image"]
    print(img)
    d = p.client.get_all_metadata()
    r = p.client.retrieve_asset_by_local_id(d[-1]["local_id"])
    print(r)

def run_delete(args):
    logger.info(f'Running deletion.')
    logger.debug(f' host: {args.host}')
    logger.debug(f' dir: {args.dir}')
    logger.debug(f' path: {args.path}')
    logger.debug(f' metadata_path: {args.metadata_path}')
    logger.debug(f' retain_duration: {args.retain_duration}')
    p = Phone(args.host)
    sync = Storage(dir=args.dir, path=args.path, metadata_path=args.metadata_path)

    # Obtain whatever we have on the phone.
    logger.info(f'Obtaining metadata from phone.')
    on_phone = p.get_all_metadata()
    logger.info(f'Total assets: {len(on_phone)}')

    # Obtain all asset collections.
    asset_collections = p.client.get_asset_collections()

    # We're only interested in manually created albums.
    manual_albums = asset_collections["albums"]

    # Collect all photos that are part of a manual album, they are always preserved.
    keep_photos = set()
    for album in manual_albums:
        for asset in album["assets"]:
            keep_photos.add(asset["local_id"])
    logger.info(f'Assets in albums: {len(keep_photos)}')

    to_prune = []
    # Next, we can iterate through the photos on the phone, check against expiry.
    now = time.time()
    for asset in on_phone:
        staleness = now - asset["modification_date"]
        logger.debug(f'Considering {asset["local_id"]} with age {staleness} seconds.')
        if staleness >= args.retain_duration:
            logger.debug(f'  is older than retain')
            if asset["local_id"] in keep_photos:
                logger.debug(f"  Preserving {asset['local_id']}  {asset['filename']} because in keep.")
            if asset["local_id"] not in keep_photos:
                logger.debug(f"  {asset['filename']} marking for deletion")
                to_prune.append(asset)

    logger.info(f'To prune: {len(to_prune)}')

    # Ok, now that we have a list of to-be-pruned entries, we have to prove to the phone that we got
    # the photo and metadata.

    logger.info(f'Calculating proof we have asset marked for deletion.')
    to_prune_proof = []
    for asset in to_prune:
        to_prune_proof.append(sync.load_from_disk(asset))
    logger.info(f'Obtained {len(to_prune_proof)} proofs.')

    # Now that we have assembled our proof, we can _finally_ tell the phone to remove these entries.
    # print(to_prune_proof)

    logger.info(f'Issuing deletion, phone will check proof and prompt.')
    p.delete_assets_by_metadata(to_prune_proof, args.ignore_integrity)
    logger.info(f'Done.')
    
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retrieval")
    parser.add_argument('-v', '--verbosity', action="count", help="Increase verbosity," 
                        "nothing is warn/error only, -v is info, -vv is debug.", default=0)

    parser.add_argument("--host", default="http://$REPL_HOST:1338", help="xmlrpc interface to connect to. Defaults to %(default)s")
    subparsers = parser.add_subparsers(dest="command")

    test_parser = subparsers.add_parser('test')
    test_parser.set_defaults(func=run_test)

    def add_storage_args(parse):
        parse.add_argument("--dir", default="/tmp/storage", help="Directory to write output to.")
        parse.add_argument("--path", default="{Y_create}-{m_create}/{filename}", help="Format to use when writing.")
        parse.add_argument("--metadata-path", default="{Y_create}-{m_create}/metadata/{filename}",
                           help="Format to use when writing metadata, extension is replaced with .json.")

    sync_parser = subparsers.add_parser('sync')
    add_storage_args(sync_parser)
    sync_parser.set_defaults(func=run_sync)

    def sane_date_parser(v):
        day = 60 * 60 * 24
        week = 7 * day
        month = 31 * day

        scaling = day
        value = float('inf')

        if v.endswith("d"):
            value = float(v[0:-1])
            scaling = day
        elif v.endswith("m"):
            value = float(v[0:-1])
            scaling = month
        elif v.endswith("w"):
            value = float(v[0:-1])
            scaling = week
        else:
            raise BaseException("Date should end with 'd' for days, 'w' for weeks, 'm' for months")

        return scaling * value

    delete_parser = subparsers.add_parser('delete', help="Remove files older than given duration and not in a manually created album.")
    add_storage_args(delete_parser)
    delete_parser.add_argument("--retain-duration", default="30d", type=sane_date_parser, help="Duration to keep. Default: %(default)s, d=day, w=week, m=month")
    delete_parser.add_argument("--ignore-integrity", default=False, action="store_true", help="Skip the integrity check.")
    delete_parser.set_defaults(func=run_delete)

    args = parser.parse_args()

    logger.setLevel(logging.WARN)
    if args.verbosity == 1:
        logger.setLevel(logging.DEBUG)
    if args.verbosity == 0:
        logger.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
        

    if "REPL_HOST" in os.environ:
        args.host = args.host.replace("$REPL_HOST", os.environ["REPL_HOST"])
    else:
        logger.warning("no REPL_HOST set, you probably want to set this or pass --host to set the hostname")

    # no command
    if (args.command is None):
        parser.print_help()
        parser.exit()

    args.func(args)

