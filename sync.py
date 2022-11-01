#!/usr/bin/env python3
import argparse
import xmlrpc.client

import os
import json

import datetime
import time
from pathlib import Path

class Phone:
    def __init__(self, url):
        self.url = url
        self.client = xmlrpc.client.ServerProxy(url, allow_none=True)

    def __getattr__(self, name):
        if hasattr(self.client, name):
            return getattr(self.client, name)

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
                to_sync.append(asset)
                continue
            # The file exists, check if modified date is the same.
            with open(path_to_metadata) as f:
                data = json.load(f)
            if data["modification_date"] != asset["modification_date"]:
                to_sync.append(asset)
                continue
            # nothing to do!
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
        retrieved = p.retrieve_asset_by_local_id(asset["local_id"])

        # Ensure directories exist.
        os.makedirs(os.path.dirname(get_path), exist_ok=True)
        os.makedirs(os.path.dirname(path_to_metadata), exist_ok=True)

        # Next, write the actual data.
        with open(get_path, "wb") as f:
            f.write(retrieved["_data"].data)

        # Read it back to obtain the md5.
        with open(get_path, "rb") as f:
            z = f.read()

        if len(z) != retrieved["_filesize"]:
            raise BaseException(f"File size incorrect for {get_path}, expected {len(z)}.")

        import hashlib
        m = hashlib.md5()
        m.update(z)
        h = m.hexdigest()
        expected = retrieved["_md5"]
        if h != expected:
            raise BaseException(f"Md5 does not match! Got {h} for {get_path}, expected {expected}")

        # we got here, file retrieved correctly, write the metadata
        clean_metadata = {k:v for k, v in retrieved.items() if not k.startswith("_")}
        # print(clean_metadata)
        with open(path_to_metadata, "w") as f:
            json.dump(clean_metadata, f)

        return retrieved

def run_sync(args):
    p = Phone(args.host)
    sync = Storage(dir=args.dir, path=args.path, metadata_path=args.metadata_path)
    on_phone = p.get_all_metadata()
    print(f"On phone: {len(on_phone)}")
    to_sync = sync.files_to_sync(on_phone)
    print(f"to sync: {len(to_sync)}")
    total = len(to_sync)
    for i, asset in enumerate(to_sync):
        retrieved = sync.retrieve(p, asset)
        filename = retrieved["filename"]
        size = retrieved["_filesize"]
        date =  datetime.datetime.utcfromtimestamp(retrieved["creation_date"]).strftime('%Y-%m-%d %H:%M:%S')
        print(f"{i+1: >5} / {total: >5}: {filename: >20} {date} ({size: >9} bytes)")

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
    p = Phone(args.host)
    sync = Storage(dir=args.dir, path=args.path, metadata_path=args.metadata_path)

    # Obtain whatever we have on the phone.
    on_phone = p.get_all_metadata()

    # Obtain all asset collections.
    asset_collections = p.client.get_asset_collections()

    # We're only interested in manually created albums.
    manual_albums = asset_collections["albums"]

    # Collect all photos that are part of a manual album, they are always preserved.
    keep_photos = set()
    for album in manual_albums:
        for asset in album["assets"]:
            keep_photos.add(asset["local_id"])

    to_prune = []
    # Next, we can iterate through the photos on the phone, check against expiry.
    now = time.time()
    for asset in on_phone:
        # print(asset)
        staleness = now - asset["modification_date"]
        # print(staleness)
        if staleness >= args.retain_duration:
            # print("  is too old")
            # if asset["local_id"] in keep_photos:
                # print(f"   Preserving {asset['local_id']}  {asset['filename']} because in keep.")
            if asset["local_id"] not in keep_photos:
                # print(f"  {asset['filename']} marking for deletion")
                to_prune.append(asset)

    # Ok, now that we have a list of to-be-pruned entries, we have to prove to the phone that we got
    # the photo and metadata.

    to_prune_proof = []
    for asset in to_prune:
        to_prune_proof.append(sync.load_from_disk(asset))

    # Now that we have assembled our proof, we can _finally_ tell the phone to remove these entries.
    print(to_prune_proof)

    p.delete_assets_by_metadata(to_prune_proof)
    
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retrieval")

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
    delete_parser.set_defaults(func=run_delete)

    args = parser.parse_args()

    if "REPL_HOST" in os.environ:
        args.host = args.host.replace("$REPL_HOST", os.environ["REPL_HOST"])

    # no command
    if (args.command is None):
        parser.print_help()
        parser.exit()

    args.func(args)

