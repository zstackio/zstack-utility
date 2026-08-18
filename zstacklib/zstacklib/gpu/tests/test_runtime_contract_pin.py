# -*- coding: utf-8 -*-

import hashlib
import json
import os
import unittest

CONTRACT_REVISION = "1.0.0"
FIXTURE_BUNDLE_SHA256 = "2fa47e71dde8b31ec5a00d8485530a7d3cb7b852df42075bceabbbb2d66c5d71"
CONTRACT_REVISION_V1_1 = "1.1.0"
FIXTURE_BUNDLE_V1_1_SHA256 = "892b6baad1384034d5bc7a5ae0cbdc351bd65a5315a1b92b0cadb2dda4bfc289"


class TestRuntimeContractPin(unittest.TestCase):
    CONTRACT_REVISION = CONTRACT_REVISION
    FIXTURE_BUNDLE_SHA256 = FIXTURE_BUNDLE_SHA256
    CONTRACT_REVISION_V1_1 = CONTRACT_REVISION_V1_1
    FIXTURE_BUNDLE_V1_1_SHA256 = FIXTURE_BUNDLE_V1_1_SHA256
    CONTRACT_PINS = (
        {
            "revision": CONTRACT_REVISION,
            "filename": "fixture-bundle-v1.json",
            "sha256": FIXTURE_BUNDLE_SHA256,
        },
        {
            "revision": CONTRACT_REVISION_V1_1,
            "filename": "fixture-bundle-v1.1.json",
            "sha256": FIXTURE_BUNDLE_V1_1_SHA256,
        },
    )

    def test_contract_revision_and_fixture_bundle_are_pinned(self):
        for pin in self.CONTRACT_PINS:
            fixture_path = os.path.join(
                os.path.dirname(__file__),
                "fixtures",
                "contracts",
                pin["filename"])
            with open(fixture_path, "rb") as stream:
                bundle = stream.read()

            document = json.loads(bundle.decode("utf-8"))
            self.assertEqual(pin["revision"], document["schemaRevision"])
            self.assertEqual(pin["sha256"], hashlib.sha256(bundle).hexdigest())


if __name__ == "__main__":
    unittest.main()
