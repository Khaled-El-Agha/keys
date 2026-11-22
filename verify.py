import sys
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def verify_file(file_path, public_key_path, sig_path):
    with open(public_key_path, "rb") as f:
        public_key = serialization.load_pem_public_key(f.read())

    with open(file_path, "rb") as f:
        data = f.read()

    with open(sig_path, "rb") as f:
        signature = f.read()

    try:
        public_key.verify(
            signature,
            data,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        print("VALID: signature matches the file and the private key that made it.")
        return True
    except InvalidSignature:
        print("INVALID: file does not match the signature (tampered, wrong file, or wrong key).")
        return False


if __name__ == "__main__":
    file_path, public_key_path, sig_path = sys.argv[1], sys.argv[2], sys.argv[3]
    verify_file(file_path, public_key_path, sig_path)
