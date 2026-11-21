from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone

STORAGE_SOURCE = "storage.json"
STORAGE_KEY = "iCubeAuthInfo://icube.cloudide"
STORAGE_ENV = "TRAE_CN_STORAGE"
APP_DIRS = ("Trae CN", "TRAE SOLO CN")

TC_MAGIC = b"tc\x05\x10\x00\x00"
TC_SALT_LEN = 32
TC_DIGEST_LEN = 64


class TraeAuthError(Exception):
    pass


# tc v5 兼容解密所需的客户端内置 KDF 常量（非用户密码，见 docs/references/PROBE.md §6.10）。
_JG = bytes([
    82, 9, 106, 213, 48, 54, 165, 56, 191, 64, 163, 158, 129, 243, 215, 251,
    124, 227, 57, 130, 155, 47, 255, 135, 52, 142, 67, 68, 196, 222, 233, 203,
    84, 123, 148, 50, 166, 194, 35, 61, 238, 76, 149, 11, 66, 250, 195, 78,
    8, 46, 161, 102, 40, 217, 36, 178, 118, 91, 162, 73, 109, 139, 209, 37,
])
_KG = bytes([
    31, 221, 168, 51, 136, 7, 199, 49, 177, 18, 16, 89, 39, 128, 236, 95,
    96, 81, 127, 169, 25, 181, 74, 13, 45, 229, 122, 159, 147, 201, 156, 239,
    160, 224, 59, 77, 174, 42, 245, 176, 200, 235, 187, 60, 131, 83, 153, 97,
    23, 43, 4, 126, 186, 119, 214, 38, 225, 105, 20, 99, 85, 33, 12, 125,
])


def _gmul(a: int, b: int) -> int:
    product = 0
    for _ in range(8):
        if b & 1:
            product ^= a
        high = a & 0x80
        a = (a << 1) & 0xFF
        if high:
            a ^= 0x1B
        b >>= 1
    return product


def _rotl8(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (8 - shift))) & 0xFF


def _build_sboxes() -> tuple[list[int], list[int]]:
    inverse = [0] * 256
    for value in range(1, 256):
        for candidate in range(1, 256):
            if _gmul(value, candidate) == 1:
                inverse[value] = candidate
                break
    sbox = [0] * 256
    for value in range(256):
        inv = inverse[value]
        sbox[value] = (inv ^ _rotl8(inv, 1) ^ _rotl8(inv, 2)
                       ^ _rotl8(inv, 3) ^ _rotl8(inv, 4) ^ 0x63)
    inv_sbox = [0] * 256
    for value, mapped in enumerate(sbox):
        inv_sbox[mapped] = value
    return sbox, inv_sbox


_SBOX, _INV_SBOX = _build_sboxes()
_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def _expand_key(key: bytes) -> list[list[int]]:
    if len(key) != 16:
        raise TraeAuthError("AES-128 密钥长度无效")
    words = [list(key[offset:offset + 4]) for offset in range(0, 16, 4)]
    for index in range(4, 44):
        temp = list(words[index - 1])
        if index % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[byte] for byte in temp]
            temp[0] ^= _RCON[index // 4 - 1]
        words.append([words[index - 4][i] ^ temp[i] for i in range(4)])
    return [sum(words[round_index * 4:round_index * 4 + 4], [])
            for round_index in range(11)]


def _inv_shift_rows(state: list[int]) -> list[int]:
    out = [0] * 16
    for column in range(4):
        for row in range(4):
            out[column * 4 + row] = state[((column - row) % 4) * 4 + row]
    return out


def _inv_mix_columns(state: list[int]) -> list[int]:
    out: list[int] = []
    for column in range(4):
        a0, a1, a2, a3 = state[column * 4:column * 4 + 4]
        out.extend([
            _gmul(a0, 14) ^ _gmul(a1, 11) ^ _gmul(a2, 13) ^ _gmul(a3, 9),
            _gmul(a0, 9) ^ _gmul(a1, 14) ^ _gmul(a2, 11) ^ _gmul(a3, 13),
            _gmul(a0, 13) ^ _gmul(a1, 9) ^ _gmul(a2, 14) ^ _gmul(a3, 11),
            _gmul(a0, 11) ^ _gmul(a1, 13) ^ _gmul(a2, 9) ^ _gmul(a3, 14),
        ])
    return out


def _decrypt_block(block: bytes, round_keys: list[list[int]]) -> bytes:
    state = list(block)
    for index in range(16):
        state[index] ^= round_keys[10][index]
    for round_index in range(9, 0, -1):
        state = _inv_shift_rows(state)
        state = [_INV_SBOX[byte] for byte in state]
        for index in range(16):
            state[index] ^= round_keys[round_index][index]
        state = _inv_mix_columns(state)
    state = _inv_shift_rows(state)
    state = [_INV_SBOX[byte] for byte in state]
    for index in range(16):
        state[index] ^= round_keys[0][index]
    return bytes(state)


def aes128_cbc_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    if not data or len(data) % 16 != 0:
        raise TraeAuthError("密文长度无效")
    if len(iv) != 16:
        raise TraeAuthError("IV 长度无效")
    round_keys = _expand_key(key)
    previous = iv
    out = bytearray()
    for offset in range(0, len(data), 16):
        block = data[offset:offset + 16]
        decrypted = _decrypt_block(block, round_keys)
        out.extend(a ^ b for a, b in zip(decrypted, previous))
        previous = block
    return bytes(out)


def _kdf(salt: bytes) -> tuple[bytes, bytes]:
    secret = bytes(a ^ b for a, b in zip(_JG, _KG))
    digest = hashlib.sha512(hashlib.sha512(salt).digest() + secret).digest()
    return digest[:16], digest[16:32]


def _unpad(data: bytes) -> bytes:
    if not data:
        raise TraeAuthError("解密结果为空")
    pad = data[-1]
    if pad < 1 or pad > 16 or data[-pad:] != bytes([pad]) * pad:
        raise TraeAuthError("解密结果填充无效")
    return data[:-pad]


def decrypt_tc_blob(blob: bytes) -> bytes:
    if len(blob) < len(TC_MAGIC) + TC_SALT_LEN + 16:
        raise TraeAuthError("凭证数据过短")
    if blob[:len(TC_MAGIC)] != TC_MAGIC:
        raise TraeAuthError("凭证数据格式未知")
    salt = blob[len(TC_MAGIC):len(TC_MAGIC) + TC_SALT_LEN]
    ciphertext = blob[len(TC_MAGIC) + TC_SALT_LEN:]
    if len(ciphertext) % 16:
        raise TraeAuthError("凭证数据不是块对齐的")
    key, iv = _kdf(salt)
    plain = _unpad(aes128_cbc_decrypt(key, iv, ciphertext))
    if len(plain) < TC_DIGEST_LEN:
        raise TraeAuthError("凭证数据缺少完整性校验")
    digest, payload = plain[:TC_DIGEST_LEN], plain[TC_DIGEST_LEN:]
    if not hmac.compare_digest(hashlib.sha512(payload).digest(), digest):
        raise TraeAuthError("凭证数据完整性校验失败")
    return payload


def parse_auth_value(value: object) -> dict:
    if not isinstance(value, str) or not value.strip():
        raise TraeAuthError("凭证数据为空")
    text = value.strip()
    try:
        if text.startswith("{"):
            payload = json.loads(text)
        else:
            payload = json.loads(decrypt_tc_blob(base64.b64decode(text)))
    except TraeAuthError:
        raise
    except (ValueError, UnicodeDecodeError) as exc:
        raise TraeAuthError("登录凭证无法解密（客户端存储格式可能已变化）") from exc
    if not isinstance(payload, dict):
        raise TraeAuthError("登录凭证结构异常")
    return payload


def _storage_candidates(env: dict, home: str) -> list[str]:
    override = (env.get(STORAGE_ENV) or "").strip()
    if override:
        return [os.path.abspath(os.path.expanduser(override))]
    base = os.path.join(home, "Library", "Application Support")
    return [os.path.join(base, app_dir, "User", "globalStorage", "storage.json")
            for app_dir in APP_DIRS]


def find_storage_path(env: dict | None = None, home: str | None = None) -> str | None:
    env = env if env is not None else os.environ
    home = home or os.path.expanduser("~")
    candidates = _storage_candidates(env, home)
    if env.get(STORAGE_ENV):
        return candidates[0]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def _parse_expiry(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class StorageCredential:
    token: str = field(repr=False)
    path: str
    expires_at: datetime | None = None
    user_id: str | None = None
    warning: str | None = None


def _check_storage_file(path: str) -> os.stat_result:
    try:
        info = os.lstat(path)
    except FileNotFoundError as exc:
        raise TraeAuthError(
            "未找到 Trae CN 登录凭证：%s 不存在；请登录 Trae CN，或用 --jwt-file/TRAE_CN_JWT 指定" % path
        ) from exc
    except OSError as exc:
        raise TraeAuthError("Trae CN 登录凭证不可读：%s（%s）" % (path, exc.strerror)) from exc
    if stat.S_ISLNK(info.st_mode):
        raise TraeAuthError("Trae CN 登录凭证是符号链接，拒绝读取：%s" % path)
    if not stat.S_ISREG(info.st_mode):
        raise TraeAuthError("Trae CN 登录凭证不是普通文件：%s" % path)
    if info.st_mode & 0o022:
        raise TraeAuthError(
            "Trae CN 登录凭证权限过宽（%04o），拒绝读取；建议 chmod 600 %s"
            % (info.st_mode & 0o777, path))
    return info


def _read_storage_entries(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise TraeAuthError("Trae CN 登录凭证不可读：%s（%s）" % (path, exc.strerror)) from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise TraeAuthError("Trae CN storage.json 不是合法 JSON：%s" % path) from exc
    if not isinstance(data, dict):
        raise TraeAuthError("Trae CN storage.json 结构异常：%s" % path)
    return data


def _auth_values(data: dict) -> list[tuple[str, object]]:
    ordered: list[tuple[str, object]] = []
    if STORAGE_KEY in data:
        ordered.append((STORAGE_KEY, data[STORAGE_KEY]))
    for key, value in data.items():
        if key.startswith("iCubeAuthInfo://") and key != STORAGE_KEY:
            ordered.append((key, value))
    return ordered


def load_storage_credential(path: str | None = None, *, env: dict | None = None,
                            home: str | None = None,
                            now: datetime | None = None) -> StorageCredential:
    env = env if env is not None else os.environ
    target = path or find_storage_path(env, home)
    if not target:
        raise TraeAuthError(
            "未找到 Trae CN 登录凭证：storage.json 不存在；请登录 Trae CN，或用 --jwt-file/TRAE_CN_JWT 指定")
    _check_storage_file(target)
    data = _read_storage_entries(target)
    values = _auth_values(data)
    if not values:
        raise TraeAuthError("Trae CN storage.json 中没有登录凭证（iCubeAuthInfo）：%s" % target)
    errors: list[str] = []
    for _key, value in values:
        try:
            payload = parse_auth_value(value)
        except TraeAuthError as exc:
            errors.append(str(exc))
            continue
        token = payload.get("token")
        if not isinstance(token, str) or not token.strip():
            errors.append("登录凭证缺少 token 字段")
            continue
        expires_at = _parse_expiry(payload.get("expiredAt"))
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        if expires_at and current >= expires_at:
            raise TraeAuthError(
                "Trae CN 登录凭证已过期（%s），请重新登录 Trae CN"
                % expires_at.astimezone().strftime("%Y-%m-%d %H:%M"))
        warning = None
        if not expires_at:
            warning = "登录凭证未包含过期时间，无法在本地预检"
        user_id = payload.get("userId")
        return StorageCredential(
            token=token.strip(), path=target, expires_at=expires_at,
            user_id=user_id if isinstance(user_id, str) else None,
            warning=warning)
    raise TraeAuthError("Trae CN 登录凭证不可用：%s" % (errors[0] if errors else "未知原因"))


def storage_info(env: dict | None = None, home: str | None = None) -> dict:
    env = env if env is not None else os.environ
    target = find_storage_path(env, home)
    info = {"source": STORAGE_SOURCE, "path": target,
            "exists": bool(target) and os.path.isfile(target),
            "readable": False, "mode": None, "size": None,
            "expires_at": None, "user_id": None, "warning": None, "error": None}
    if not target:
        info["error"] = ("未找到 Trae CN 登录凭证：storage.json 不存在；"
                         "请登录 Trae CN，或用 --jwt-file/TRAE_CN_JWT 指定")
        return info
    if not info["exists"]:
        info["error"] = ("未找到 Trae CN 登录凭证：storage.json 不存在（%s）；"
                         "请登录 Trae CN，或用 --jwt-file/TRAE_CN_JWT 指定" % target)
        return info
    try:
        stat_info = _check_storage_file(target)
    except TraeAuthError as exc:
        info["error"] = str(exc)
        try:
            stat_info = os.stat(target)
            info["mode"] = stat_info.st_mode & 0o777
            info["size"] = stat_info.st_size
        except OSError:
            pass
        return info
    info["readable"] = os.access(target, os.R_OK)
    info["mode"] = stat_info.st_mode & 0o777
    info["size"] = stat_info.st_size
    if stat_info.st_mode & 0o044:
        info["warning"] = (
            "Trae CN 登录凭证权限过宽（%04o），其他用户可读；建议 chmod 600 %s"
            % (info["mode"], target))
    return info
