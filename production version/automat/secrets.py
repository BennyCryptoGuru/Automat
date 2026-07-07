import ctypes
from ctypes import wintypes


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class SecretVault:
    """Protect credentials with the current Windows user's DPAPI key."""

    def __init__(self):
        if not hasattr(ctypes, "windll"):
            raise RuntimeError("Encrypted login profiles require Windows")
        self.crypt32 = ctypes.windll.crypt32
        self.kernel32 = ctypes.windll.kernel32

    @staticmethod
    def _blob(data):
        buffer = ctypes.create_string_buffer(data)
        return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer

    def encrypt(self, value):
        raw = str(value).encode("utf-8")
        source, keepalive = self._blob(raw)
        output = _DataBlob()
        if not self.crypt32.CryptProtectData(
            ctypes.byref(source), "Automat", None, None, None, 0x01, ctypes.byref(output)
        ):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            self.kernel32.LocalFree(output.pbData)

    def decrypt(self, encrypted):
        source, keepalive = self._blob(bytes(encrypted))
        output = _DataBlob()
        if not self.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0x01, ctypes.byref(output)
        ):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
        finally:
            self.kernel32.LocalFree(output.pbData)
