# Copyright 2015-2017 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#

import os
import uuid

from vdsm.storage import blockSD
from vdsm.storage import constants as sc
from vdsm.storage import clusterlock
from vdsm.storage import sd

from monkeypatch import MonkeyPatchScope
from testlib import VdsmTestCase, recorded
from testlib import make_uuid
from testlib import expandPermutations, permutations

from storage.storagetestlib import (
    fake_block_env,
    fake_file_env,
    make_file_volume,
)

MB = 1048576

# We want to create volumes larger than the minimum block volume size
# (currently 128M)
VOLSIZE = 256 * MB


class ManifestMixin(object):

    def test_init_failure_raises(self):
        def fail(*args):
            raise RuntimeError("injected failure")

        with self.env() as env:
            with MonkeyPatchScope([(clusterlock, 'initSANLock', fail)]):
                with self.assertRaises(RuntimeError):
                    env.sd_manifest.initDomainLock()


class TestFileManifest(ManifestMixin, VdsmTestCase):
    env = fake_file_env

    def setUp(self):
        self.img_id = str(uuid.uuid4())
        self.vol_id = str(uuid.uuid4())

    def test_get_monitoring_path(self):
        with self.env() as env:
            self.assertEqual(env.sd_manifest.metafile,
                             env.sd_manifest.getMonitoringPath())

    def test_getvsize(self):
        with self.env() as env:
            make_file_volume(env.sd_manifest, VOLSIZE,
                             self.img_id, self.vol_id)
            self.assertEqual(VOLSIZE, env.sd_manifest.getVSize(
                self.img_id, self.vol_id))

    def test_getvallocsize(self):
        with self.env() as env:
            make_file_volume(env.sd_manifest, VOLSIZE,
                             self.img_id, self.vol_id)
            self.assertEqual(0, env.sd_manifest.getVAllocSize(
                self.img_id, self.vol_id))

    def test_getisodomainimagesdir(self):
        with self.env() as env:
            isopath = os.path.join(env.sd_manifest.domaindir, sd.DOMAIN_IMAGES,
                                   sd.ISO_IMAGE_UUID)
            self.assertEqual(isopath, env.sd_manifest.getIsoDomainImagesDir())

    def test_getmdpath(self):
        with self.env() as env:
            sd_manifest = env.sd_manifest
            mdpath = os.path.join(sd_manifest.domaindir, sd.DOMAIN_META_DATA)
            self.assertEqual(mdpath, env.sd_manifest.getMDPath())

    def test_getmetaparam(self):
        with self.env() as env:
            sd_manifest = env.sd_manifest
            self.assertEqual(sd_manifest.sdUUID,
                             sd_manifest.getMetaParam(sd.DMDK_SDUUID))

    def test_getallimages(self):
        with self.env() as env:
            self.assertEqual(set(), env.sd_manifest.getAllImages())
            img_id = str(uuid.uuid4())
            vol_id = str(uuid.uuid4())
            make_file_volume(env.sd_manifest, VOLSIZE, img_id, vol_id)
            self.assertIn(img_id, env.sd_manifest.getAllImages())

    def test_purgeimage_race(self):
        with self.env() as env:
            sd_id = env.sd_manifest.sdUUID
            img_id = str(uuid.uuid4())
            vol_id = str(uuid.uuid4())
            make_file_volume(env.sd_manifest, VOLSIZE, img_id, vol_id)

            env.sd_manifest.deleteImage(sd_id, img_id, None)
            # Simulate StorageDomain.imageGarbageCollector by removing the
            # deleted image directory.
            deleted_dir = env.sd_manifest.getDeletedImagePath(img_id)
            env.sd_manifest.oop.fileUtils.cleanupdir(deleted_dir)
            # purgeImage should not raise if the image was already removed
            env.sd_manifest.purgeImage(sd_id, img_id, [vol_id], False)


class TestBlockManifest(ManifestMixin, VdsmTestCase):
    env = fake_block_env

    def test_get_monitoring_path(self):
        with self.env() as env:
            md_lv_path = env.lvm.lvPath(env.sd_manifest.sdUUID, sd.METADATA)
            self.assertEqual(md_lv_path, env.sd_manifest.getMonitoringPath())

    def test_getvsize_active_lv(self):
        # Tests the path when the device file is present
        with self.env() as env:
            vg_name = env.sd_manifest.sdUUID
            lv_name = str(uuid.uuid4())
            env.lvm.createLV(vg_name, lv_name, VOLSIZE / MB)
            env.lvm.fake_lv_symlink_create(vg_name, lv_name)
            self.assertEqual(VOLSIZE,
                             env.sd_manifest.getVSize('<imgUUID>', lv_name))

    def test_getvsize_inactive_lv(self):
        # Tests the path when the device file is not present
        with self.env() as env:
            lv_name = str(uuid.uuid4())
            env.lvm.createLV(env.sd_manifest.sdUUID, lv_name, VOLSIZE / MB)
            self.assertEqual(VOLSIZE,
                             env.sd_manifest.getVSize('<imgUUID>', lv_name))

    def test_getmetaparam(self):
        with self.env() as env:
            self.assertEqual(env.sd_manifest.sdUUID,
                             env.sd_manifest.getMetaParam(sd.DMDK_SDUUID))

    def test_getblocksize_defaults(self):
        with self.env() as env:
            self.assertEqual(512, env.sd_manifest.logBlkSize)
            self.assertEqual(512, env.sd_manifest.phyBlkSize)

    def test_overwrite_blocksize(self):
        metadata = {sd.DMDK_VERSION: 3,
                    blockSD.DMDK_LOGBLKSIZE: 2048,
                    blockSD.DMDK_PHYBLKSIZE: 1024}
        with self.env() as env:
            # Replacing the metadata will not overwrite these values since they
            # are set only in the manifest constructor.
            env.sd_manifest.replaceMetadata(metadata)
            self.assertEqual(512, env.sd_manifest.logBlkSize)
            self.assertEqual(512, env.sd_manifest.phyBlkSize)

            # If we supply values in the metadata used to construct the
            # manifest then those values will apply.
            new_manifest = blockSD.BlockStorageDomainManifest(
                env.sd_manifest.sdUUID, metadata)
            self.assertEqual(2048, new_manifest.logBlkSize)
            self.assertEqual(1024, new_manifest.phyBlkSize)


@expandPermutations
class TestBlockDomainMetadataSlot(VdsmTestCase):

    @permutations([
        # used_slots, free_slot
        # Note: the first 4 slots (0-3) are reserved for domain metadata
        ([], 4),
        ([4], 5),
        ([5], 4),
        ([4, 6], 5),
        ([4, 7], 5),
    ])
    def test_metaslot_selection(self, used_slots, free_slot):
        with fake_block_env() as env:
            for offset in used_slots:
                lv = make_uuid()
                sduuid = env.sd_manifest.sdUUID
                env.lvm.createLV(sduuid, lv, VOLSIZE / MB)
                tag = sc.TAG_PREFIX_MD + str(offset)
                env.lvm.addtag(sduuid, lv, tag)
            with env.sd_manifest.acquireVolumeMetadataSlot(None, 1) as mdSlot:
                self.assertEqual(mdSlot, free_slot)

    def test_metaslot_lock(self):
        with fake_block_env() as env:
            with env.sd_manifest.acquireVolumeMetadataSlot(None, 1):
                acquired = env.sd_manifest._lvTagMetaSlotLock.acquire(False)
                self.assertFalse(acquired)


class StorageDomainManifest(sd.StorageDomainManifest):
    def __init__(self):
        pass

    @recorded
    def acquireDomainLock(self, host_id):
        pass

    @recorded
    def releaseDomainLock(self):
        pass

    @recorded
    def dummy(self):
        pass


class TestDomainLock(VdsmTestCase):

    def test_domainlock_contextmanager(self):
        expected_calls = [("acquireDomainLock", (1,), {}),
                          ("dummy", (), {}),
                          ("releaseDomainLock", (), {})]
        manifest = StorageDomainManifest()
        with manifest.domain_lock(1):
            manifest.dummy()
        self.assertEqual(manifest.__calls__, expected_calls)

    def test_domainlock_contextmanager_exception(self):
        class InjectedFailure(Exception):
            pass

        expected_calls = [("acquireDomainLock", (1,), {}),
                          ("releaseDomainLock", (), {})]
        manifest = StorageDomainManifest()
        with self.assertRaises(InjectedFailure):
            with manifest.domain_lock(1):
                raise InjectedFailure()
        self.assertEqual(manifest.__calls__, expected_calls)
