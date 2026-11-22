import sys
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def sign_file(file_path, private_key_path, sig_path):
    with open(private_key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    with open(file_path, "rb") as f:
        data = f.read()

    signature = private_key.sign(
        data,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )

    with open(sig_path, "wb") as f:
        f.write(signature)

    print(f"Signed {file_path} -> {sig_path}")


if __name__ == "__main__":
    file_path, private_key_path, sig_path = sys.argv[1], sys.argv[2], sys.argv[3]
    sign_file(file_path, private_key_path, sig_path)
