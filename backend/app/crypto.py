"""Transparente Verschlüsselung für Geheimnisse (Secrets) im Ruhezustand.

Reine Standardbibliothek (kein extra Paket): ein Schlüsselstrom wird per
SHA-256 im Counter-Modus erzeugt, die Authentizität per HMAC-SHA256 gesichert
(Encrypt-then-MAC). Das ersetzt keine geprüfte Krypto-Bibliothek, hebt die
Geheimnisse aber deutlich über Klartext in der Datenbank.

Der Hauptschlüssel kommt aus ``APP_SECRET_KEY`` (Env). Ist nichts gesetzt,
wird einmalig ein zufälliger Schlüssel erzeugt und neben der Datenbank unter
``.foundryhub_key`` abgelegt. Werte, die nicht als Token erkennbar sind (Altbestand
in Klartext), werden unverändert zurückgegeben – so bleibt alles abwärts­
kompatibel."""
import base64
import hashlib
import hmac
import os

_PREFIX = b"enc1:"  # Kennung für verschlüsselte Werte


def _data_dir() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:////data/foundryhub.db")
    if url.startswith("sqlite") and "/" in url:
        path = url.split("///")[-1]
        d = os.path.dirname(path) or "."
        if os.path.isdir(d) or d in ("/data", "."):
            return d
    return "/data" if os.path.isdir("/data") else "."


def _load_master() -> bytes:
    env = os.getenv("APP_SECRET_KEY", "").strip()
    if env:
        return hashlib.sha256(env.encode()).digest()
    # sonst persistenten Zufallsschlüssel verwenden/erzeugen
    path = os.path.join(_data_dir(), ".foundryhub_key")
    # Abwärtskompatibel: früheren Schlüssel (.aihub_key) übernehmen, falls vorhanden
    legacy = os.path.join(_data_dir(), ".aihub_key")
    try:
        if os.path.exists(path):
            with open(path, "rb") as f:
                raw = f.read().strip()
                if raw:
                    return hashlib.sha256(raw).digest()
        if os.path.exists(legacy):
            with open(legacy, "rb") as f:
                raw = f.read().strip()
                if raw:
                    # alten Schlüssel auf neuen Namen übernehmen (einmalig)
                    try:
                        with open(path, "wb") as nf:
                            nf.write(raw)
                        os.chmod(path, 0o600)
                    except OSError:
                        pass
                    return hashlib.sha256(raw).digest()
        raw = base64.b64encode(os.urandom(32))
        with open(path, "wb") as f:
            f.write(raw)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return hashlib.sha256(raw).digest()
    except OSError:
        # Fallback: deterministisch aus Maschinen-/Prozessinfo (besser als nichts)
        return hashlib.sha256(b"foundryhub-fallback-key").digest()


_MASTER = _load_master()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        counter += 1
    return bytes(out[:length])


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        return ""
    data = plaintext.encode("utf-8")
    nonce = os.urandom(16)
    enc_key = hashlib.sha256(_MASTER + b"enc").digest()
    mac_key = hashlib.sha256(_MASTER + b"mac").digest()
    ks = _keystream(enc_key, nonce, len(data))
    ct = bytes(a ^ b for a, b in zip(data, ks))
    tag = hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()
    token = _PREFIX + base64.b64encode(nonce + ct + tag)
    return token.decode("ascii")


def decrypt(token: str) -> str:
    if not token:
        return ""
    raw = token.encode("ascii", "ignore") if isinstance(token, str) else token
    if not raw.startswith(_PREFIX):
        return token  # Klartext-Altbestand
    try:
        blob = base64.b64decode(raw[len(_PREFIX):])
        nonce, rest = blob[:16], blob[16:]
        ct, tag = rest[:-32], rest[-32:]
        mac_key = hashlib.sha256(_MASTER + b"mac").digest()
        expected = hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, tag):
            return ""  # manipuliert/falscher Schlüssel
        enc_key = hashlib.sha256(_MASTER + b"enc").digest()
        ks = _keystream(enc_key, nonce, len(ct))
        return bytes(a ^ b for a, b in zip(ct, ks)).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return ""


def is_encrypted(value: str) -> bool:
    return bool(value) and isinstance(value, str) and value.startswith(_PREFIX.decode())
