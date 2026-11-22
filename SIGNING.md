# File Signing & Verification — Concept and Commands

## The idea in simple terms

A digital signature proves two things about a file at once:

1. **Integrity** — the file hasn't been changed since it was signed.
2. **Authenticity** — whoever signed it had the private key (i.e. it's really from them).

It works with a **key pair**:

- **Private key** — kept secret, only used to *sign*.
- **Public key** — shared freely, only used to *verify*.

### What signing does

1. Hash the file (SHA-256) → a short fingerprint. Change one byte of the file and the fingerprint changes completely.
2. Encrypt that hash with the **private key** → this encrypted blob is the **signature**.

### What verification does

1. Hash the file you have *right now* (SHA-256) → fingerprint A.
2. Decrypt the signature using the **public key** → this recovers the fingerprint the signer originally signed → fingerprint B.
3. **Compare fingerprint A to fingerprint B.**

```
hash(file right now)  ==  hash recovered from signature ?
```

- **Match → VALID.** The file is unchanged, and it was signed by whoever holds the matching private key (only that private key produces a signature the public key can correctly unlock).
- **No match → INVALID.** Either the file was modified after signing, the signature belongs to a different file, or the wrong key pair is being used.

The private key never has to leave the signer's machine — the public key alone is enough for anyone to check a signature, but it's useless for forging one.

---

## Step-by-step: shell commands (OpenSSL)

### 1. Generate a key pair (only done once)

```bash
# private key (keep this secret, never share/commit it)
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out private.pem

# derive the public key from it (safe to share)
openssl pkey -in private.pem -pubout -out public.pem
```

### 2. Sign a file

```bash
openssl dgst -sha256 -sign private.pem -out firmware.sig firmware.bin
```

- `-sha256` → hash algorithm used on the file
- `-sign private.pem` → private key used to encrypt the hash
- `-out firmware.sig` → the resulting signature file
- `firmware.bin` → the file being signed

### 3. Verify a file

```bash
openssl dgst -sha256 -verify public.pem -signature firmware.sig firmware.bin
```

- `-verify public.pem` → public key used to decrypt the signature back into a hash
- `-signature firmware.sig` → the signature to check
- `firmware.bin` → the file to re-hash and compare against

Output is either:

```
Verified OK
```

or

```
Verification Failure
```

### 4. Prove it actually catches tampering

```bash
# modify the file after it was signed
echo "extra byte" >> firmware.bin

# verify again with the same signature — now it fails
openssl dgst -sha256 -verify public.pem -signature firmware.sig firmware.bin
# -> Verification Failure
```

Or check a signature against the *wrong* file entirely:

```bash
openssl dgst -sha256 -verify public.pem -signature firmware.sig firmware2.bin
# -> Verification Failure
```

Both fail for the same reason: the hash computed from the file no longer matches the hash recovered from the signature.

---

## CSRs and certificates — where does the signature live?

So far the signature was a **separate file** (`firmware.sig`) next to the data it covers (`firmware.bin`). A **CSR (Certificate Signing Request)** and a **certificate** work differently: the signature is **embedded inside the same file**, as a trailing field of its own structure. There's no sibling `.sig` file.

A CSR bundles three things into one structure (PKCS#10):

1. **Subject info** — CN, O, etc. (who/what this key belongs to)
2. **Your public key**
3. **Signature** — the private key signs (1)+(2), and the result is appended as a field at the end of the same structure

### 1. Generate a CSR

```bash
openssl req -new -key private.pem -out firmware.csr -subj "/CN=firmware-signer/O=DemoOrg"
```

- `-key private.pem` → private key used to sign the CSR's contents
- `-subj ...` → the subject info being signed over
- `-out firmware.csr` → output file containing data **and** signature together

### 2. Look inside it

```bash
openssl req -in firmware.csr -text -noout
```

Output ends with exactly the signature, appended after the data it covers:

```
Certificate Request:
    Data:
        Subject: CN = firmware-signer, O = DemoOrg
        Subject Public Key Info: ...        <- your public key, embedded here
    Signature Algorithm: sha256WithRSAEncryption
    Signature Value:
        66:29:43:6b:99:7a:02:46:...          <- the signature, embedded here
```

The base64 blob between `-----BEGIN/END CERTIFICATE REQUEST-----` in `firmware.csr` *is* that whole structure (data + signature) encoded as one piece. So: **the private key signs the subject+public-key block, and the signature becomes a trailing field of the same CSR file** — it travels with the data, not alongside it.

This is a self-signature at this stage: it only proves "whoever submitted this CSR holds the private key matching this public key." It is not yet trusted by anyone.

### 3. Turn the CSR into a certificate — using a separate CA key pair

This is the realistic setup: the CA has **its own key pair**, completely different from `private.pem`/`public.pem`. The applicant's key only ever signs the CSR; the CA's key is what signs the certificate.

```bash
# the CA's own key pair (nothing to do with firmware's key pair)
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out ca-private.pem
openssl pkey -in ca-private.pem -pubout -out ca-public.pem

# the CA's own self-signed root certificate — this is the trust anchor everyone
# must already have/trust ahead of time (this is where the CA signs its own Data
# block with its own key, since there's no higher authority above a root CA)
openssl req -x509 -new -key ca-private.pem -days 3650 \
  -subj "/CN=Demo Root CA/O=DemoOrg" -out ca.crt

# the CA signs firmware.csr using the CA's PRIVATE key (not firmware's key)
openssl x509 -req -in firmware.csr -CA ca.crt -CAkey ca-private.pem \
  -CAcreateserial -days 365 -out firmware.crt
```

Inspect the result:

```bash
openssl x509 -in firmware.crt -text -noout
```

```
Certificate:
    Data:
        Issuer: CN = Demo Root CA, O = DemoOrg      <- who signed it (the CA)
        Validity: ...
        Subject: CN = firmware-signer, O = DemoOrg  <- who it was issued to
        Subject Public Key Info: ...                <- firmware's PUBLIC key
    Signature Algorithm: sha256WithRSAEncryption
    Signature Value: ...                            <- made by the CA's PRIVATE key
```

Compared to the self-signed CSR from step 2, the certificate now adds:

- **`Issuer`** — identifies the CA, and is now *different* from `Subject` (in the CSR/self-signed case they were the same)
- **`Serial Number`** — unique id the CA assigns to this certificate
- **`Validity`** — not-before / not-after dates the CA decided
- **`Signature Value`** — produced by the **CA's private key**, not firmware's private key

Firmware's private key never touches this step at all — it already did its job (proving key possession) back when it signed the CSR.

### 4. Verify the certificate using the CA

```bash
openssl verify -CAfile ca.crt firmware.crt
# -> firmware.crt: OK
```

This recovers the hash from `Signature Value` using the **CA's public key** (embedded inside `ca.crt`) and compares it to a fresh hash of the certificate's `Data` block — same compare-two-hashes mechanic as everywhere else in this document.

If you verify against a *different* CA's certificate, it fails — because that CA's public key can't unlock a signature made by a different CA's private key:

```bash
openssl verify -CAfile some-other-ca.crt firmware.crt
# -> error 20: unable to get local issuer certificate
# -> verification failed
```

---

## mTLS — how the private key gets used, live

One correction to the framing first: in a live mTLS connection, the party checking the client's certificate is the **TLS server**, not the CA. The CA's work already happened earlier and offline, when it signed the CSR. The server isn't on the phone with the CA during the handshake — it just needs the CA's root certificate (`ca.crt`) already sitting in its trust store, so it can check signatures itself.

So the private key (`private.pem`) actually gets used **twice, for two different purposes**:

| When | What it signs | Proves to | Frequency |
|---|---|---|---|
| CSR creation | the subject + public key block | the CA | once, offline, at issuance time |
| TLS handshake | a hash of the live handshake transcript | the server | every single connection |

The certificate (`firmware.crt`) is what's exchanged on the wire. The private key itself **never leaves the client** — only a fresh signature produced by it does, every time a connection is made.

### What happens in the handshake (TLS 1.3, mutual auth)

1. Server sends `CertificateRequest` — this is the part that makes it "mutual": the server is demanding the client also prove who it is.
2. Client sends `Certificate` — this is just `firmware.crt`: subject, public key, and the CA's signature over it. No private key material here.
3. Client sends `CertificateVerify` — the client's **private key signs a hash of the entire handshake so far** (the two ClientHello/ServerHello messages, the certificate just sent, etc). This is the live proof: "I hold the private key matching the public key in the certificate I just handed you."
4. Server checks two independent things, both reusing the same compare-two-hashes mechanic from the top of this document:
   - Is `firmware.crt`'s signature valid under a CA the server already trusts (`ca.crt`)? → authenticity of the *identity*.
   - Does `CertificateVerify`'s signature check out against the **public key embedded in `firmware.crt`**? → proof the client actually holds the matching *private key*, right now, for *this* connection.
5. The server does the exact same thing back (sends its own `Certificate` + `CertificateVerify`), and the client verifies the server the same way — that's the "mutual" in mTLS.

Only if both checks pass does the handshake finish.

### Reproduce it locally

```bash
# give the server its own identity, signed by the same CA
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out server-private.pem
openssl req -new -key server-private.pem -out server.csr -subj "/CN=localhost/O=DemoOrg"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca-private.pem -CAcreateserial -days 365 -out server.crt

# start a TLS server that demands a client certificate
openssl s_server -accept 4433 -cert server.crt -key server-private.pem -CAfile ca.crt -Verify 1 -quiet &

# client connects, presenting firmware.crt and proving possession of private.pem
echo -e "GET / HTTP/1.0\r\n\r\n" | openssl s_client -connect localhost:4433 \
  -cert firmware.crt -key private.pem -CAfile ca.crt -quiet
```

Output shows both sides verifying each other's chain:

```
depth=1 CN = Demo Root CA, O = DemoOrg
verify return:1
depth=0 CN = firmware-signer, O = DemoOrg      <- server accepted the client's cert
verify return:1
depth=1 CN = Demo Root CA, O = DemoOrg
verify return:1
depth=0 CN = localhost, O = DemoOrg            <- client accepted the server's cert
verify return:1
```

Add `-msg` to `s_client` to see the actual handshake messages — `CertificateRequest`, `Certificate`, and `CertificateVerify` flowing in both directions (`>>>` client→server, `<<<` server→client):

```
<<< TLS 1.3, Handshake, CertificateRequest   (server asks client to prove identity)
<<< TLS 1.3, Handshake, Certificate          (server's own cert)
<<< TLS 1.3, Handshake, CertificateVerify    (server signs transcript w/ its private key)
>>> TLS 1.3, Handshake, Certificate          (client sends firmware.crt)
>>> TLS 1.3, Handshake, CertificateVerify    (client signs transcript w/ private.pem)
```

That second `CertificateVerify` line is the moment `private.pem` gets used — not to get the certificate issued (that already happened), but to prove, live, that this connection is really coming from whoever holds that key.
