#!/usr/bin/env python3
import datetime
import re
import socket
import time
from xmlrpc.server import DocXMLRPCServer

from objc_util import ObjCInstance


class PhotoService:
    """
    Class to expose the photos module through an xml rpc interface.
    """

    def __init__(self):
        # Use a local instance instance of photos in case we ever want to hook methods.
        import photos

        self.p = photos
        """
        # This wasn't too useful, can't marshall the types.
        for z in dir(photos):
            if z.startswith("_"):
                continue
            setattr(self, z, getattr(photos, z))
        """

    def get_all_metadata_worker(self, include_burst=False):
        """
        Retrieve all metadata of all images and videos.
        """
        all_assets = []
        image_assets = self.p.get_assets(media_type="image")
        for image_asset in image_assets:
            serializable = self._make_serializable(image_asset)
            all_assets.append(serializable)

            if include_burst:
                burst_photos_for_asset = self.retrieve_burst_assets_by_local_id(
                    image_asset.local_id
                )
                for bi, burst_photo in enumerate(burst_photos_for_asset):
                    burst_serializable = self._make_serializable(
                        burst_photo, burst_index=bi
                    )
                    burst_serializable["location"] = serializable["location"]
                    all_assets.append(burst_serializable)
        for video in list(self.p.get_assets(media_type="video")):
            video = self._make_serializable(video)

            all_assets.append(video)

        return all_assets

    def get_all_metadata(self):
        return self.get_all_metadata_worker(include_burst=False)

    def get_all_metadata_with_burst(self):
        return self.get_all_metadata_worker(include_burst=True)

    def get_asset_collections(self):
        """
        Get all asset collections.
        """
        assetcollections = {
            "albums": self._make_serializable(self.p.get_albums()),
            "smart_albums": self._make_serializable(self.p.get_smart_albums()),
            "moments": self._make_serializable(self.p.get_moments()),
            "favorites_album": self._make_serializable(self.p.get_favorites_album()),
            "recently_added_album": self._make_serializable(
                self.p.get_recently_added_album()
            ),
            "selfies_album": self._make_serializable(self.p.get_selfies_album()),
            "screenshots_album": self._make_serializable(
                self.p.get_screenshots_album()
            ),
        }
        return assetcollections

    def delete_assets_by_metadata(self, list_of_asset_metadata, ignore_integrity=False):
        """
        Remove list of assets. Metadata provides strong guarantees that the asset was correctly
        transfered.
        """
        to_delete = []

        for metadata in list_of_asset_metadata:
            local_id = metadata["local_id"]
            on_phone_metadata = self.retrieve_asset_by_local_id(local_id)
            # Discard the data key.
            del on_phone_metadata["_data"]
            if on_phone_metadata == metadata:
                to_delete.append(self.p.get_asset_with_local_id(local_id))
            else:
                print("Something is not matching:")
                print("   Metadata Phone: {}".format(on_phone_metadata))
                print("   Metadata Local: {}".format(metadata))
                if ignore_integrity:
                    print("Deleting regardless, as integrity check passed.")
                    to_delete.append(self.p.get_asset_with_local_id(local_id))
                else:
                    print("Integrity check required to pass, aborting.")
                    return

        print(to_delete)
        self.p.batch_delete(to_delete)

    @staticmethod
    def _asset_filename(a):
        return str(ObjCInstance(a).filename())

    @staticmethod
    def _get_data(asset):
        if asset.media_type == "image":
            # image_b = asset.get_image_data(original=True)
            # print(image_b.uti)
            # image_bytes = image_b.getvalue()
            return PhotoService._get_image_data(asset)
        if asset.media_type == "video":
            image_b = PhotoService._get_video_data(asset)
            image_bytes = image_b
        return image_bytes

    @staticmethod
    def _get_video_data(asset):
        # https://forum.omz-software.com/topic/3299/get-filenames-for-photos-from-camera-roll/18
        # https://gist.github.com/jsbain/de01d929d3477a4c8e7ae9517d5b3d70
        from objc_util import ObjCBlock, ObjCClass, ObjCInstance, c_void_p

        assets = [asset]
        options = ObjCClass("PHVideoRequestOptions").new()
        options.version = (
            1  # PHVideoRequestOptionsVersionOriginal, use 0 for edited versions.
        )
        image_manager = ObjCClass("PHImageManager").defaultManager()

        handled_assets = []

        def handleAsset(_obj, asset, audioMix, info):
            A = ObjCInstance(asset)
            """I am just appending to handled_assets to process later"""
            handled_assets.append(A)
            """
            # alternatively, handle inside handleAsset.  maybe need a threading.Lock here to ensure you are not sending storbinaries in parallel
            with open(str(A.resolvedURL().resourceSpecifier()),'rb') as fp:
                fro.storbinary(......)
            """

        handlerblock = ObjCBlock(
            handleAsset,
            argtypes=[
                c_void_p,
            ]
            * 4,
        )

        for A in assets:
            # these are PHAssets
            image_manager.requestAVAssetForVideo(
                A, options=options, resultHandler=handlerblock
            )

        while len(handled_assets) < len(assets):
            time.sleep(0.1)

        A = handled_assets[0]
        with open(str(A.resolvedURL().fileSystemRepresentation(), "ascii"), "rb") as fp:
            return fp.read()

    @staticmethod
    def _get_image_data(asset):
        print("_get_image_data arg", asset)
        # adapted from get_video_data
        # https://forum.omz-software.com/topic/3299/get-filenames-for-photos-from-camera-roll/18
        # https://gist.github.com/jsbain/de01d929d3477a4c8e7ae9517d5b3d70
        import ctypes

        import objc_util
        from objc_util import ObjCBlock, ObjCClass, ObjCInstance, c_void_p

        assets = [asset]
        options = ObjCClass("PHImageRequestOptions").new()
        options.PHImageRequestOptionsDeliveryMode = 1  # high quality
        options.version = 0
        options.synchronous = True
        image_manager = ObjCClass("PHImageManager").defaultManager()

        handled_assets = []

        def handleAsset(_obj, result, info):
            # result here holds the thing we actually want.
            A = ObjCInstance(result)
            handled_assets.append(A)

        handlerblock = ObjCBlock(
            handleAsset,
            argtypes=[
                c_void_p,
            ]
            * 3,
        )

        for A in assets:
            # https://developer.apple.com/documentation/photokit/phimagemanager/3237282-requestimagedataandorientationfo?language=objc
            image_manager.requestImageDataAndOrientationForAsset(
                A, options=options, resultHandler=handlerblock
            )

        while len(handled_assets) < len(assets):
            # print(".");
            time.sleep(0.1)

        # Now we have some clunky bytes object that makes up a pointer and a length, retrieve the
        # heic data.
        retrieved_data = handled_assets[0]
        ptr = retrieved_data.bytes()
        data = ctypes.POINTER(ctypes.c_char).from_buffer(ptr)[: retrieved_data.length()]

        return data

    def retrieve_asset_by_local_id(self, local_id):
        """
        Function to retrieve an asset by its local id, with full metdata and the extra keys:
        - _filesize the number of bytes making up the file
        - _data The data of this file.
        - _md5 The md5 sum of this file.
        """
        asset = self.p.get_asset_with_local_id(local_id)

        asset_dict = self._make_serializable(asset)
        image_bytes = self._get_data(asset)
        asset_dict["_filesize"] = len(image_bytes)
        asset_dict["_data"] = image_bytes

        import hashlib

        m = hashlib.md5()
        m.update(image_bytes)
        asset_dict["_md5"] = m.hexdigest()

        return asset_dict

    def retrieve_asset_by_local_id_or_burst(self, flat_asset):
        try:
            return self.retrieve_asset_by_local_id(flat_asset["local_id"])
        except ValueError as e:
            if not "burst_id" in flat_asset:
                raise ValueError(
                    "local id lookup failed, and no burst_id present in asset: ",
                    str(flat_asset),
                )

        from objc_util import ObjCBlock, ObjCClass, ObjCInstance, c_void_p

        # Retrieve all entries in this burst id.
        entries = self.retrieve_burst_assets_by_burst_id(flat_asset["burst_id"])

        # That got us a list of PHAsset pointers.
        for bi, asset in enumerate(entries):
            asset_dict = self._make_serializable(asset, burst_index=bi)
            if asset_dict["local_id"] == flat_asset["local_id"]:
                # yay, this is the one we are interested in!
                image_bytes = PhotoService._get_image_data(asset)
                asset_dict["_filesize"] = len(image_bytes)
                asset_dict["_data"] = image_bytes
                import hashlib

                m = hashlib.md5()
                m.update(image_bytes)
                asset_dict["_md5"] = m.hexdigest()

                return asset_dict
        raise ValueError("Failed to find asset from burst for ", str(flat_asset))

    def retrieve_phasset_by_local_id(self, local_id):
        """
        Returns a PHAsset pointer, or a None
        """
        # Next, try to fetch the asset using its global id.
        from objc_util import ObjCBlock, ObjCClass, ObjCInstance, c_void_p

        options = ObjCClass("PHFetchOptions").new()
        rawclass = ObjCClass("PHAsset")

        r = rawclass.fetchAssetsWithLocalIdentifiers_options_([local_id], options)

        for i in range(r.count()):
            as_phasset = r.objectAtIndex(i)
            return as_phasset

    def retrieve_burst_assets_by_local_id(self, local_id):
        """
        Returns a list of PHAsset pointers of the burst assets that are underneath this local id.
        These can be passed to _get_image_data
        """
        from objc_util import ObjCBlock, ObjCClass, ObjCInstance, c_void_p

        ph_asset_for_localid = self.retrieve_phasset_by_local_id(local_id)
        if ph_asset_for_localid is None:
            return []

        rawclass = ObjCClass("PHAsset")
        options = ObjCClass("PHFetchOptions").new()
        options.includeAllBurstAssets = True
        burst_id = ph_asset_for_localid.burstIdentifier()
        return self.retrieve_burst_assets_by_burst_id(burst_id)

    def retrieve_burst_assets_by_burst_id(self, burst_id):
        from objc_util import ObjCBlock, ObjCClass, ObjCInstance, c_void_p

        rawclass = ObjCClass("PHAsset")
        options = ObjCClass("PHFetchOptions").new()
        options.includeAllBurstAssets = True
        r = rawclass.fetchAssetsWithBurstIdentifier_options_(burst_id, options)

        res = []

        for i in range(r.count()):
            burst_photo_as_phasset = r.objectAtIndex(i)
            res.append(burst_photo_as_phasset)
        return res

    def _make_serializable(self, a, burst_index=None):
        """
        This function can convert any photos' data type into a dictionary
        of usefulness.
        """
        ASSETCOLLECTION_DATA_KEYS = (
            "local_id",
            "assets",
            "title",
            "type",
            "subtype",
            "start_date",
            "end_date",
        )
        ASSET_DATA_KEYS = (
            "local_id",
            "pixel_width",
            "pixel_height",
            "media_type",
            "media_subtypes",
            "creation_date",
            "modification_date",
            "hidden",
            "favorite",
            "duration",
            "location",
        )
        if isinstance(a, list):
            z = [self._make_serializable(b) for b in a]
            return z

        if isinstance(a, self.p.AssetCollection):
            z = {}
            for k in ASSETCOLLECTION_DATA_KEYS:
                z[k] = self._make_serializable(getattr(a, k))
            return z

        if isinstance(a, self.p.Asset):
            z = {}
            for k in ASSET_DATA_KEYS:
                z[k] = self._make_serializable(getattr(a, k))
            z["filename"] = PhotoService._asset_filename(a)
            return z

        if (
            hasattr(a, "_get_objc_classname")
            and a._get_objc_classname() == b"__NSTaggedDate"
        ):
            interval = a.timeIntervalSince1970()
            return float(interval)

        if hasattr(a, "_get_objc_classname") and a._get_objc_classname() == b"PHAsset":
            from objc_util import (
                ObjCBlock,
                ObjCClass,
                ObjCInstance,
                c_void_p,
                create_objc_class,
            )

            """
            {'local_id': 'ADsdfsdfsdfAB0/L0/001', 
            'pixel_width': 3024, 'pixel_height': 4032, 'media_type': 'image', 
            'media_subtypes': [], 'creation_date': x.0, 'modification_date': x.0, 'hidden': False, 
            'favorite': False, 'duration': 0.0, 'location': {'longitude': -x.x, 'latitude': x.x, 'altitude': x.x}, 
            'filename': 'IMG_6474.JPG'}
            """
            z = {}
            z["local_id"] = str(a.localIdentifier())
            z["burst_id"] = str(a.burstIdentifier()) if a.burstIdentifier() else None
            if z["burst_id"] and burst_index is None:
                raise ValueError(
                    "_make_serializable called for burst without burst_index argument"
                )

            z["pixel_width"] = int(a.pixelWidth())
            z["pixel_height"] = int(a.pixelHeight())
            media_type = a.mediaType()
            if media_type == 1:
                z["media_type"] = "image"
            elif media_type == 2:  # probably?
                z["media_type"] = "video"
            elif media_type == 3:  # probably?
                z["media_type"] = "audio"
            d = a.creationDate()
            z["creation_date"] = float(self._make_serializable(a.creationDate()))
            z["modification_date"] = float(
                self._make_serializable(a.modificationDate())
            )
            z["hidden"] = bool(a.hidden())
            z["favorite"] = bool(a.favorite())
            z["duration"] = float(a.duration())

            def location_to_location_dict(CCLocation_struct):
                # This is super cringe, but all attempts to just read the fields failed, and this
                # is for burst photos only anyway, so it doesn't matter much.
                """
                print("location _get_objc_classname:", a.location()._get_objc_classname())
                # print("\n".join(sorted(dir(a.location().coordinate))))
                print("name:", a.location().coordinate.name)
                print("obj:", a.location().coordinate.obj)
                # z = ObjCInstance(a.location().coordinate.obj)
                z = ObjCInstance(a.location().coordinate().longitude())
                print(z)
                print("coordinate:", a.location().coordinate.get("longitude"))
                print("coordinate:", a.location.coordinate())
                """
                text = str(CCLocation_struct)
                results = re.findall("<(.*),(.*)>", text)
                return float(results[0][0]), float(results[0][1])

            latitude, longitude = location_to_location_dict(a.location())

            z["location"] = {
                "longitude": longitude,
                "latitude": latitude,
                "altitude": None,
                "timestamp": z["creation_date"],
            }
            base_filename = PhotoService._asset_filename(a)
            start, ext = base_filename.split(".")
            z["filename"] = start + "_{:0>2}".format(burst_index) + "." + ext
            return z

        if hasattr(a, "_get_objc_classname"):
            raise ValueError(
                "Unhandled objc entity passed, got: " + a._get_objc_classname()
            )

        if isinstance(a, datetime.datetime):
            return time.mktime(a.timetuple())

        # we do not need to recurse / modify, return as is.
        return a


class ReuseableDocXMLServer(DocXMLRPCServer):
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)


def disable_idle():
    import console
    from objc_util import on_main_thread

    on_main_thread(console.set_idle_timer_disabled)(True)


def start():
    with ReuseableDocXMLServer(("0.0.0.0", 1338), allow_none=True) as server:
        server.set_server_title("Photo management server")
        server.set_server_name("Photo management server")

        server.register_instance(PhotoService(), allow_dotted_names=True)
        # server.register_multicall_functions()
        print("Serving XML-RPC on localhost port 1338")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nKeyboard interrupt received, exiting.")


def test_image_data():
    p = PhotoService()
    entries = p.get_all_metadata()

    a_photo = [x for x in entries if x["media_type"] == "image"]
    desired = a_photo[-1]
    for z in a_photo:
        if z["filename"].startswith("IMG_6514_03.JPG"):
            # print(z)
            desired = z
    print("desired:", desired)
    a = p.retrieve_asset_by_local_id_or_burst(desired)
    # print(desired)
    # print(a)
    # d = p._get_image_data(a)
    print("yes, all done")

    # Next, try to fetch the asset using its global id.
    from objc_util import ObjCBlock, ObjCClass, ObjCInstance, c_void_p

    asset = ObjCClass("PHAsset").new().init()
    options = ObjCClass("PHFetchOptions").new()
    options.includeAllBurstAssets = True
    print(options)
    # print("\n".join(sorted(dir(asset))))
    print("just phasset")
    # print("\n".join(sorted(dir(ObjCClass("PHAsset")))))
    rawclass = ObjCClass("PHAsset")

    r = rawclass.fetchAssetsWithLocalIdentifiers_options_(
        [desired["local_id"]], options
    )

    burst_id = None
    print(r.count())
    for i in range(r.count()):
        as_phasset = r.objectAtIndex(i)
        print(as_phasset.burstIdentifier())
        print(as_phasset.representsBurst())
        burst_id = as_phasset.burstIdentifier()

    # Now, how do we retrieve the images from a burst identifier? >_<
    if burst_id is None:
        return

    rawclass = ObjCClass("PHAsset")
    options = ObjCClass("PHFetchOptions").new()
    options.includeAllBurstAssets = True

    r = rawclass.fetchAssetsWithBurstIdentifier_options_(burst_id, options)
    print(r.count())
    for i in range(r.count()):
        as_phasset = r.objectAtIndex(i)
        print(as_phasset)
        d = p._get_image_data(as_phasset)
        print(len(d))
        local_id = str(as_phasset.localIdentifier())
        print(local_id)
        print(type(local_id))
        # bah, that needs a burst id :/
        # as_local_asset = p.p.get_asset_with_local_id(local_id)
        # print(as_local_asset)
        # print(as_phasset.burstSelectionTypes())

    burstres = p.retrieve_burst_assets_by_local_id(desired["local_id"])
    print(burstres)


if __name__ == "__main__":
    disable_idle()
    start()
