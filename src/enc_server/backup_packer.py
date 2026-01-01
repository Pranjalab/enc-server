import os
import tarfile
import shutil
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.exceptions import InvalidTag

class BackupPacker:
    MAGIC = b'ENCBKP01'
    SALT_SIZE = 16
    NONCE_SIZE = 12
    # Argon2id Parameters for Key Derivation (Strong security)
    mem_cost = 65536 # 64MB
    time_cost = 4
    parallelism = 2
    hash_len = 32 # ChaCha20Poly1305 key size

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        kdf = Argon2id(
            salt=salt,
            length=self.hash_len,
            iterations=self.time_cost,
            lanes=self.parallelism,
            memory_cost=self.mem_cost,
            ad=None,
            secret=None
        )
        return kdf.derive(password.encode())

    def pack(self, source_dir: str, output_file: str, password: str):
        """
        Compress source_dir into a tarball, encrypt it, and write to output_file.
        Format: [MAGIC][SALT][NONCE][CIPHERTEXT]
        """
        # 1. Create temporary tarball
        tmp_tar = output_file + ".tmp.tar"
        try:
            with tarfile.open(tmp_tar, "w:gz") as tar:
                tar.add(source_dir, arcname=os.path.basename(source_dir))
            
            with open(tmp_tar, "rb") as f:
                plaintext = f.read()
        finally:
            if os.path.exists(tmp_tar):
                os.remove(tmp_tar)

        # 2. Encrypt
        salt = os.urandom(self.SALT_SIZE)
        nonce = os.urandom(self.NONCE_SIZE)
        key = self._derive_key(password, salt)
        chacha = ChaCha20Poly1305(key)
        
        # Authenticated encryption
        ciphertext = chacha.encrypt(nonce, plaintext, self.MAGIC)

        # 3. Write Output
        with open(output_file, "wb") as f:
            f.write(self.MAGIC)
            f.write(salt)
            f.write(nonce)
            f.write(ciphertext)

    def unpack(self, input_file: str, dest_dir: str, password: str):
        """
        Decrypt input_file, unpack tarball to dest_dir.
        """
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Backup file not found: {input_file}")

        with open(input_file, "rb") as f:
            magic = f.read(len(self.MAGIC))
            if magic != self.MAGIC:
                raise ValueError("Invalid backup file format (Magic bytes mismatch)")
            
            salt = f.read(self.SALT_SIZE)
            nonce = f.read(self.NONCE_SIZE)
            ciphertext = f.read()

        # Decrypt
        try:
            key = self._derive_key(password, salt)
            chacha = ChaCha20Poly1305(key)
            plaintext = chacha.decrypt(nonce, ciphertext, self.MAGIC)
        except InvalidTag:
            raise ValueError("Decryption failed. Incorrect password or corrupted file.")

        # Unpack Tar
        tmp_tar = input_file + ".tmp.tar"
        try:
            with open(tmp_tar, "wb") as f:
                f.write(plaintext)
            
            with tarfile.open(tmp_tar, "r:gz") as tar:
                # Security: check for path traversal? 
                # tarfile.extractall is potentially unsafe if archives are malicious.
                # Assuming backup is trusted (self-created).
                tar.extractall(path=dest_dir)
                # Note: tar extraction creates the internal directory name. 
                # If we want to exact to dest_dir precisely, we might need to handle names.
                # For now, assuming standard pack/unpack behaves mirror-like.
                # Actually, pack adds 'arcname=basename(source_dir)'. 
                # If source was /home/user/.enc_cipher, basename is .enc_cipher.
                # Extracting to /home/user/ will create .enc_cipher.
                
        finally:
             if os.path.exists(tmp_tar):
                os.remove(tmp_tar)
