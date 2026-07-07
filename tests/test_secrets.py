from automat.secrets import SecretVault


def test_dpapi_round_trip_and_ciphertext_is_not_plaintext():
    vault = SecretVault()
    encrypted = vault.encrypt("citlive-heslo")

    assert b"citlive-heslo" not in encrypted
    assert vault.decrypt(encrypted) == "citlive-heslo"
