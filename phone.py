#!/usr/bin/env python3
import datetime
from xmlrpc.server import DocXMLRPCServer
import socket

import time


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

    def get_all_metadata(self):
        """
            Retrieve all metadata of all images and videos.
        """
        all_assets = self.p.get_assets(media_type="image")
        all_assets.extend(list(self.p.get_assets(media_type="video")))
        flat = [self._make_serializable(z) for z in all_assets]
        return flat

    def get_asset_collections(self):
        """
            Get all asset collections.
        """
        assetcollections = {
                            "albums": self._make_serializable(self.p.get_albums()),
                            "smart_albums": self._make_serializable(self.p.get_smart_albums()),
                            "moments": self._make_serializable(self.p.get_moments()),
                            "favorites_album": self._make_serializable(self.p.get_favorites_album()),
                            "recently_added_album": self._make_serializable(self.p.get_recently_added_album()),
                            "selfies_album": self._make_serializable(self.p.get_selfies_album()),
                            "screenshots_album": self._make_serializable(self.p.get_screenshots_album()),
                        }
        return assetcollections

    def delete_assets_by_metadata(self, list_of_asset_metadata):
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
                print("Something is not matching, bailing!")
                return

        print(to_delete)
        self.p.batch_delete([to_delete[1]])

    @staticmethod
    def _asset_filename(a):
        return str(ObjCInstance(a).filename())


    @staticmethod
    def _get_data(asset):
        if (asset.media_type == "image"):
            image_b = asset.get_image_data(original=True)
            image_bytes = image_b.getvalue()
        if (asset.media_type == "video"):
            image_b = PhotoService._get_video_data(asset)
            image_bytes = image_b
        return image_bytes


    @staticmethod
    def _get_video_data(asset):
        # https://forum.omz-software.com/topic/3299/get-filenames-for-photos-from-camera-roll/18
        # https://gist.github.com/jsbain/de01d929d3477a4c8e7ae9517d5b3d70
        from objc_util import ObjCInstance, ObjCClass, ObjCBlock, c_void_p
        assets = [asset]
        options = ObjCClass('PHVideoRequestOptions').new()
        options.version = 1	#PHVideoRequestOptionsVersionOriginal, use 0 for edited versions.
        image_manager = ObjCClass('PHImageManager').defaultManager()

        handled_assets = []

        def handleAsset(_obj,asset, audioMix, info):
            A = ObjCInstance(asset)
            '''I am just appending to handled_assets to process later'''
            handled_assets.append(A)
            '''
            # alternatively, handle inside handleAsset.  maybe need a threading.Lock here to ensure you are not sending storbinaries in parallel
            with open(str(A.resolvedURL().resourceSpecifier()),'rb') as fp:
                fro.storbinary(......)
            '''
            
        handlerblock=ObjCBlock(handleAsset, argtypes=[c_void_p,]*4)

        for A in assets:
            #these are PHAssets
            image_manager.requestAVAssetForVideo(A, 
                                options=options, 
                                resultHandler=handlerblock)
                                
        while len(handled_assets) < len(assets):
            time.sleep(0.1)

        A = handled_assets[0]
        with open(str(A.resolvedURL().resourceSpecifier()),'rb') as fp:
            return fp.read()


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


    def _make_serializable(self, a):
        """
            This function can convert any photos' data type into a dictionary
            of usefulness.
        """
        ASSETCOLLECTION_DATA_KEYS = ("local_id",
                                     "assets",
                                     "title",
                                     "type",
                                     "subtype",
                                     "start_date",
                                     "end_date")
        ASSET_DATA_KEYS = ("local_id",
                           "pixel_width",
                           "pixel_height",
                           "media_type",
                           "media_subtypes",
                           "creation_date",
                           "modification_date",
                           "hidden",
                           "favorite",
                           "duration",
                           "location")
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
            

        if isinstance(a, datetime.datetime):
            return time.mktime(a.timetuple())

        # we do not need to recurse / modify, return as is.
        return a


class ReuseableDoxXMLServer(DocXMLRPCServer):
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)

def disable_idle():
    from objc_util import on_main_thread
    import console
    on_main_thread(console.set_idle_timer_disabled)(True);

def start():
    with ReuseableDoxXMLServer(("0.0.0.0", 1338), allow_none=True) as server:
        server.set_server_title("Photo management server")
        server.set_server_name("Photo management server")

        server.register_instance(PhotoService(), allow_dotted_names=True)
        #server.register_multicall_functions()
        print('Serving XML-RPC on localhost port 1338')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nKeyboard interrupt received, exiting.")

if __name__ == "__main__":
    disable_idle()
    start()
