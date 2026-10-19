"""Offline synthetic TLS fixture generator reused from the reviewed SDK suite preparer."""
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress

PARTNER = "demo-partner/partners/online/beijing_food"
LEADER = "demo-leader/leader/atr"
FIXTURES = (PARTNER + "/server.pem", PARTNER + "/server.key", PARTNER + "/client.pem", PARTNER + "/client.key",
            PARTNER + "/trust-bundle.pem", LEADER + "/client.pem", LEADER + "/client.key", LEADER + "/trust-bundle.pem")
PARTNER_CN = "1.2.156.3088.1.1.TESTCA.TEST01.TEST01.0001"
LEADER_CN = "1.2.156.3088.1.1.TESTCA.TEST01.TEST02.0002"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def make_tls():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Offline SDK test fixture"),
                         x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic SDK suite CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=2)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=None, decipher_only=None), critical=True).sign(ca_key, hashes.SHA256()))
    pem = lambda cert: cert.public_bytes(serialization.Encoding.PEM)
    leaves = {}
    for role, cn in (("partner-server", PARTNER_CN), ("partner-client", PARTNER_CN), ("leader-client", LEADER_CN)):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Offline SDK test fixture"),
                          x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(ca.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=2)).add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                x509.UniformResourceIdentifier("acps://" + cn)]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True,
                data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=None, decipher_only=None), critical=True).sign(ca_key, hashes.SHA256()))
        leaves[role] = (pem(cert), key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
            dict(common_name=cn, certificate_sha256=sha(pem(cert)), public_key_sha256=sha(key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)),
                valid_from_utc=cert.not_valid_before_utc.isoformat(), valid_until_utc=cert.not_valid_after_utc.isoformat(),
                extended_key_usage=["serverAuth", "clientAuth"], SAN=["localhost", "127.0.0.1", "acps://" + cn]))
    assert leaves["partner-server"][2]["public_key_sha256"] != leaves["partner-client"][2]["public_key_sha256"]
    files = {PARTNER + "/server.pem": leaves["partner-server"][0], PARTNER + "/server.key": leaves["partner-server"][1],
        PARTNER + "/client.pem": leaves["partner-client"][0], PARTNER + "/client.key": leaves["partner-client"][1],
        PARTNER + "/trust-bundle.pem": pem(ca), LEADER + "/client.pem": leaves["leader-client"][0],
        LEADER + "/client.key": leaves["leader-client"][1], LEADER + "/trust-bundle.pem": pem(ca)}
    assert set(files) == set(FIXTURES)
    return files, dict(test_only=True, registered_platform_identity_used=False, CA_private_key_persisted=False,
        CA_certificate_sha256=sha(pem(ca)), leaves={role: row[2] for role, row in leaves.items()},
        expected_fixture_paths=list(FIXTURES), private_keys_publication_allowed=False)
