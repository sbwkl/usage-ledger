import base64
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.usage_ledger.trae_auth import (TraeAuthError, aes128_cbc_decrypt,
                                        decrypt_tc_blob, find_storage_path,
                                        load_storage_credential,
                                        parse_auth_value, storage_info)

VALID_B64 = (
    "dGMFEAAAAAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh941U4IPp5aAsK2dhrJFHJBvoEhRW1e+EkBz"
    "VbMTIiWgkiULczd/1mkEBonbLeCfTf+LLNwafJB3HN/X/2cGgOkvQEdtna8VvWC49J2BTqw3r+PR15UpZ99/KU"
    "jn4NRFSqE0kOnHepEPjjz9C85ZIcksvhD7IzwEFah73s3rq1f8DPhDUGEXvpOO/5WXCNxPCvyYvySd7BUSTqsI"
    "606RQGzO95MZmM85hepIAehOhE7mCkSQjN7b3pA4/iluz79LkT09J59L5fim5YWIDXZQV9sLL3Uh9LG+jihcgO"
    "hsTAj7OFFVlfLH9KlCSbXySTkiRMsOwLPbXx9xAOtE+Db95s5pu0MDQcfizOQbBn5FGb8qNS0j3tXWG+D76HrC"
    "xlTnKYbG8UsV83Vj9fnCBIlD0OI5PtITN7QjTD96MXRtJksUEZLFR6nbt++orPPnZuf836xtz/tM/X+IletZ6"
    "CwG1vCyzzf6z647V3ksgU5H0zn1b2SGxxczQgZn/FWnDzpDrszm/Ul3U5SJL0xR+mEZWE5"
)
EXPIRED_B64 = (
    "dGMFEAAAAAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh9rtj7EfdyUnekWH+C0HRGcBH2hh9tiA45n1Z"
    "ljqSTXVAiK8mHWWX497kXRMNgu3RI/7IHoTW5WKmvRohIjC8i5eMmZ1fR5oL1kADO2Y2YWuMymIutpN5D5204/"
    "Fb7urXkOqKeECxx1h/caBn3p8P5k8pzlholGyui5BYDhuDEJMd/cN5kDUYwFslrneMkv/B0fiXvcPQ7LKQCptQ"
    "Pk6NKBjLj7s+8q4lM1C1ZAmfD+1OQMUSPGgY/seCKRF5E5f3wmqs5YJfdUlDRKp2nKY0X31wYeR34KSlPY8j/Q"
    "d4Ycd/l5sn2XWkBESDX8uOoD00U/gWR1YkSv+/kplQvGKvqT23fdUfULjamIvaYWCWcxjAB4IEoio6V+Tm3SLa"
    "sHtkl8Ql/+Jy1UrEUxvEH841c/QF1E1PaLHSV4DtSC0UZTKJpKplaFx1qdNLan2lobhNa2R8Fp4Vak9BAVyF6y"
    "Nr2cbRXEj1AbWLZRrb8qwlrVh31wwOqAOzyC5UrpaQ4YTczWNT8Mvcr29/VpbsNr4jAA"
)


class AesVectorTest(unittest.TestCase):
    def test_nist_sp800_38a_f21(self):
        key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
        iv = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        ciphertext = bytes.fromhex(
            "7649abac8119b246cee98e9b12e9197d"
            "5086cb9b507219ee95db113a917678b2"
            "73bed6b8e3c1743b7116e69e22229516"
            "3ff1caa1681fac09120eca307586e1a7")
        plaintext = bytes.fromhex(
            "6bc1bee22e409f96e93d7e117393172a"
            "ae2d8a571e03ac9c9eb76fac45af8e51"
            "30c81c46a35ce411e5fbc1191a0a52ef"
            "f69f2445df4f9b17ad2b417be66c3710")
        self.assertEqual(aes128_cbc_decrypt(key, iv, ciphertext), plaintext)


class TcBlobTest(unittest.TestCase):
    def test_decrypts_valid_blob(self):
        payload = json.loads(decrypt_tc_blob(base64.b64decode(VALID_B64)))
        self.assertEqual(payload["token"], "test-token-not-real")
        self.assertEqual(payload["userId"], "1234567890123456")

    def test_integrity_failure_rejected(self):
        blob = bytearray(base64.b64decode(VALID_B64))
        blob[-1] ^= 0x01
        with self.assertRaises(TraeAuthError) as caught:
            decrypt_tc_blob(bytes(blob))
        self.assertNotIn("test-token", str(caught.exception))

    def test_bad_magic_rejected(self):
        blob = bytearray(base64.b64decode(VALID_B64))
        blob[0] = 0x00
        with self.assertRaises(TraeAuthError):
            decrypt_tc_blob(bytes(blob))

    def test_plaintext_json_supported(self):
        payload = parse_auth_value('{"token": "plain-token"}')
        self.assertEqual(payload["token"], "plain-token")


class StorageCredentialTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "storage.json")

    def tearDown(self):
        self.tmp.cleanup()

    def write_storage(self, value, key="iCubeAuthInfo://icube.cloudide"):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({key: value}, fh)
        os.chmod(self.path, 0o600)

    def test_reads_cloudide_token(self):
        self.write_storage(VALID_B64)
        credential = load_storage_credential(self.path)
        self.assertEqual(credential.token, "test-token-not-real")
        self.assertEqual(credential.user_id, "1234567890123456")
        self.assertEqual(credential.path, self.path)
        self.assertNotIn("test-token", repr(credential))
        self.assertEqual(credential.expires_at,
                         datetime(2030, 1, 2, 3, 4, 5, 678000, tzinfo=timezone.utc))

    def test_expired_token_rejected(self):
        self.write_storage(EXPIRED_B64)
        with self.assertRaises(TraeAuthError) as caught:
            load_storage_credential(self.path)
        self.assertIn("过期", str(caught.exception))
        self.assertIn("重新登录", str(caught.exception))
        self.assertNotIn("test-token", str(caught.exception))

    def test_missing_token_rejected(self):
        self.write_storage(json.dumps({"expiredAt": "2030-01-01T00:00:00Z"}))
        with self.assertRaises(TraeAuthError):
            load_storage_credential(self.path)

    def test_missing_file_error_is_safe(self):
        missing = os.path.join(self.tmp.name, "missing.json")
        with self.assertRaises(TraeAuthError) as caught:
            load_storage_credential(missing)
        self.assertIn("未找到 Trae CN 登录凭证", str(caught.exception))

    def test_scans_other_authinfo_keys(self):
        self.write_storage(VALID_B64, key="iCubeAuthInfo://icube.custom")
        credential = load_storage_credential(self.path)
        self.assertEqual(credential.token, "test-token-not-real")

    def test_storage_info_is_secret_free(self):
        self.write_storage(VALID_B64)
        info = storage_info(env={"TRAE_CN_STORAGE": self.path})
        self.assertTrue(info["exists"])
        self.assertTrue(info["readable"])
        self.assertEqual(info["mode"], 0o600)
        self.assertIsNone(info["user_id"])
        self.assertIsNone(info["expires_at"])
        self.assertIsNone(info["error"])
        dumped = json.dumps(info)
        self.assertNotIn("test-token", dumped)
        self.assertNotIn("refresh", dumped.lower())

    def test_storage_info_does_not_decrypt(self):
        self.write_storage(VALID_B64)
        with patch("src.usage_ledger.trae_auth.load_storage_credential",
                   side_effect=AssertionError("metadata probe must not read")):
            info = storage_info(env={"TRAE_CN_STORAGE": self.path})
        self.assertTrue(info["readable"])
        self.assertIsNone(info["error"])

    def test_info_reports_permission_problem(self):
        self.write_storage(VALID_B64)
        os.chmod(self.path, 0o666)
        info = storage_info(env={"TRAE_CN_STORAGE": self.path})
        self.assertIn("权限", info["error"])

    def test_find_storage_path_override(self):
        self.write_storage(VALID_B64)
        self.assertEqual(find_storage_path(env={"TRAE_CN_STORAGE": self.path}),
                         self.path)

    def test_find_storage_path_absent(self):
        self.assertIsNone(find_storage_path(env={}, home=self.tmp.name))

    def test_rejects_symlinked_file(self):
        real = os.path.join(self.tmp.name, "real.json")
        with open(real, "w", encoding="utf-8") as fh:
            json.dump({}, fh)
        os.symlink(real, self.path)
        with self.assertRaises(TraeAuthError) as caught:
            load_storage_credential(self.path)
        self.assertIn("符号链接", str(caught.exception))

    def test_rejects_world_writable_file(self):
        self.write_storage(VALID_B64)
        os.chmod(self.path, 0o666)
        with self.assertRaises(TraeAuthError) as caught:
            load_storage_credential(self.path)
        self.assertIn("权限", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
