"""Interactive Brokers OAuth 1.0a — hosted Web API auth (no gateway to run).

IBKR's OAuth 1.0a for api.ibkr.com is more involved than E*TRADE's: a Live Session Token
(LST) is negotiated via a Diffie-Hellman exchange whose request is signed with RSA-SHA256,
and every subsequent API call is then signed with HMAC-SHA256 using the LST. All secrets
(consumer key, access token/secret, RSA private keys, DH prime) come from the environment —
never hardcoded, never sent to the client.

Env:
    IBKR_OAUTH_CONSUMER_KEY        registered consumer key
    IBKR_OAUTH_ACCESS_TOKEN        access token from IBKR self-service
    IBKR_OAUTH_ACCESS_TOKEN_SECRET base64 of the RSA-encrypted access-token secret
    IBKR_OAUTH_SIGNATURE_KEY       RSA private key PEM (signing)     — or *_FILE path
    IBKR_OAUTH_ENCRYPTION_KEY      RSA private key PEM (encryption)  — or *_FILE path
    IBKR_OAUTH_DH_PRIME            Diffie-Hellman prime (hex)
    IBKR_OAUTH_DH_GENERATOR        DH generator (default 2)
    IBKR_OAUTH_REALM               realm (default "limited_poa")
    IBKR_OAUTH_BASE_URL            default https://api.ibkr.com/v1/api

Docs: IBKR "Web API — OAuth 1.0a" (interactivebrokers.github.io / IBKR self-service portal).
This is provided for users with IBKR-issued OAuth credentials; it activates only when they
are set. Request-signing is unit-tested; the live DH/LST path requires real IBKR keys.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets as _secrets
import time
from urllib.parse import quote

try:
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
except Exception:  # noqa: BLE001
    hashes = serialization = padding = None  # type: ignore

DEFAULT_BASE = "https://api.ibkr.com/v1/api"


class IBKROAuthError(Exception):
    pass


def _pct(s: str) -> str:
    return quote(str(s), safe="~")


def _env_key(name: str) -> str | None:
    """Read a PEM either directly (IBKR_OAUTH_X) or from a file (IBKR_OAUTH_X_FILE)."""
    v = os.environ.get(name)
    if v:
        return v.replace("\\n", "\n")
    p = os.environ.get(name + "_FILE")
    if p and os.path.exists(p):
        return open(p).read()
    return None


class IBKROAuth:
    def __init__(self):
        self.consumer_key = os.environ.get("IBKR_OAUTH_CONSUMER_KEY", "")
        self.access_token = os.environ.get("IBKR_OAUTH_ACCESS_TOKEN", "")
        self.access_token_secret = os.environ.get("IBKR_OAUTH_ACCESS_TOKEN_SECRET", "")
        self.signature_pem = _env_key("IBKR_OAUTH_SIGNATURE_KEY")
        self.encryption_pem = _env_key("IBKR_OAUTH_ENCRYPTION_KEY")
        self.dh_prime = os.environ.get("IBKR_OAUTH_DH_PRIME", "")
        self.dh_generator = int(os.environ.get("IBKR_OAUTH_DH_GENERATOR", "2"))
        self.realm = os.environ.get("IBKR_OAUTH_REALM", "limited_poa")
        self.base = os.environ.get("IBKR_OAUTH_BASE_URL", DEFAULT_BASE).rstrip("/")
        self._lst: str | None = None
        self._lst_exp: float = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.consumer_key and self.access_token and self.access_token_secret
                    and self.signature_pem and self.encryption_pem and self.dh_prime)

    # ── crypto primitives ───────────────────────────────────────────────────────
    def _priv(self, pem: str):
        if serialization is None:
            raise IBKROAuthError("the 'cryptography' library is not available")
        return serialization.load_pem_private_key(pem.encode(), password=None)

    def _rsa_sha256_sign(self, data: bytes) -> bytes:
        return self._priv(self.signature_pem).sign(data, padding.PKCS1v15(), hashes.SHA256())

    def _rsa_decrypt(self, ciphertext: bytes) -> bytes:
        return self._priv(self.encryption_pem).decrypt(ciphertext, padding.PKCS1v15())

    @staticmethod
    def _to_bytes(n: int) -> bytes:
        """Java BigInteger.toByteArray(): big-endian, with a leading 0x00 if the MSB is set."""
        length = (n.bit_length() + 7) // 8 or 1
        b = n.to_bytes(length, "big")
        if b and (b[0] & 0x80):
            b = b"\x00" + b
        return b

    def _oauth_params(self, method_sig: str) -> dict:
        return {
            "oauth_consumer_key": self.consumer_key,
            "oauth_nonce": _secrets.token_hex(16),
            "oauth_signature_method": method_sig,
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self.access_token,
        }

    @staticmethod
    def _base_string(method: str, url: str, params: dict) -> str:
        norm = "&".join(f"{_pct(k)}={_pct(params[k])}" for k in sorted(params))
        return f"{method.upper()}&{_pct(url)}&{_pct(norm)}"

    # ── Live Session Token (DH + RSA-SHA256) ────────────────────────────────────
    def _live_session_token(self) -> str:
        if not self.configured:
            raise IBKROAuthError("IBKR OAuth is not configured")
        if requests is None:
            raise IBKROAuthError("the 'requests' library is not available")
        p = int(self.dh_prime, 16)
        a = int.from_bytes(_secrets.token_bytes(32), "big")
        A = pow(self.dh_generator, a, p)                      # DH challenge
        url = f"{self.base}/oauth/live_session_token"
        oauth = self._oauth_params("RSA-SHA256")
        oauth["diffie_hellman_challenge"] = format(A, "x")
        # prepend = hex of the RSA-decrypted access-token secret
        decrypted = self._rsa_decrypt(base64.b64decode(self.access_token_secret))
        prepend = decrypted.hex()
        base = prepend + self._base_string("POST", url, oauth)
        oauth["oauth_signature"] = base64.b64encode(self._rsa_sha256_sign(base.encode())).decode()
        header = "OAuth realm=\"%s\", " % self.realm + ", ".join(
            f'{_pct(k)}="{_pct(v)}"' for k, v in oauth.items())
        r = requests.post(url, headers={"Authorization": header,
                                        "User-Agent": "artikBroker"}, timeout=15)
        if r.status_code != 200:
            raise IBKROAuthError(f"live_session_token HTTP {r.status_code}: {r.text[:160]}")
        d = r.json()
        B = int(d["diffie_hellman_response"], 16)
        K = pow(B, a, p)
        lst = base64.b64encode(hmac.new(self._to_bytes(K), decrypted, hashlib.sha1).digest()).decode()
        # verify the LST against IBKR's signature
        calc = hmac.new(base64.b64decode(lst), self.consumer_key.encode(), hashlib.sha1).hexdigest()
        if calc != d.get("live_session_token_signature"):
            raise IBKROAuthError("live session token verification failed")
        self._lst = lst
        self._lst_exp = int(d.get("live_session_token_expiration", 0)) / 1000.0
        return lst

    def _lst_valid(self) -> str:
        if self._lst and time.time() < self._lst_exp - 60:
            return self._lst
        return self._live_session_token()

    # ── per-request HMAC-SHA256 signing ─────────────────────────────────────────
    def auth_header(self, method: str, url: str, query: dict | None = None) -> str:
        lst = self._lst_valid()
        oauth = self._oauth_params("HMAC-SHA256")
        all_params = dict(query or {})
        all_params.update(oauth)
        base = self._base_string(method, url, all_params)
        sig = base64.b64encode(hmac.new(base64.b64decode(lst), base.encode(), hashlib.sha256).digest()).decode()
        oauth["oauth_signature"] = sig
        return "OAuth realm=\"%s\", " % self.realm + ", ".join(
            f'{_pct(k)}="{_pct(v)}"' for k, v in oauth.items())

    def ssodh_init(self) -> dict:
        """Open the brokerage session (required once after LST for the Web API)."""
        url = f"{self.base}/iserver/auth/ssodh/init"
        q = {"publish": "true", "compete": "true"}
        r = requests.post(url, params=q,
                          headers={"Authorization": self.auth_header("POST", url, q),
                                   "User-Agent": "artikBroker"}, timeout=15)
        try:
            return r.json()
        except ValueError:
            return {"status": r.status_code}
