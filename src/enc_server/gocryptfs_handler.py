import os
import subprocess
from pathlib import Path
from rich.console import Console

console = Console()

class GocryptfsHandler:
    def __init__(self, enc_root=None):
        if enc_root:
            self.enc_root = Path(enc_root)
        else:
            self.enc_root = Path.home() / ".enc"
            
        self.vault_root = self.enc_root / "vault" / "master"
        self.run_root = self.enc_root / "run" / "master"
        
        # Ensure roots exist
        self.vault_root.mkdir(parents=True, exist_ok=True)
        self.run_root.mkdir(parents=True, exist_ok=True)

    def init_project(self, project_name, password):
        """Initialize a new encrypted project vault."""
        cipher_dir = self.vault_root / project_name
        
        if cipher_dir.exists():
             console.print(f"[yellow]Project {project_name} already exists.[/yellow]")
             return False, "Project already exists"
             
        cipher_dir.mkdir(parents=True)
        
        # Use temp file for password to avoid stdin pipe issues in non-interactive/SSH environments
        import tempfile
        passfile_path = None
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tf:
                tf.write(password)
                passfile_path = tf.name
            
            # Secure the temp file (though standard tempfile usually does proper perms, explicit is safe)
            os.chmod(passfile_path, 0o600)

            cmd = ["gocryptfs", "-init", "-q", "-passfile", passfile_path, str(cipher_dir)]
            console.print(f"Initializing vault at {cipher_dir}...")
            
            # Run without piping (inherit output to capture errors in logs if any)
            res = subprocess.run(cmd, capture_output=True, text=True)
            
            if res.returncode != 0:
                raise Exception(f"Gocryptfs init failed: {res.stderr}")

            console.print(f"[green]Vault initialized for {project_name}[/green]")

            # Auto-mount after initialization
            return self.mount_project(project_name, password)
            
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            # cleanup vault if empty
            if cipher_dir.exists() and not any(cipher_dir.iterdir()):
                cipher_dir.rmdir()
            return False, str(e)
        finally:
             if passfile_path and os.path.exists(passfile_path):
                 os.unlink(passfile_path)

    def mount_project(self, project_name, password):
        """Mount the project to the run directory."""
        cipher_dir = self.vault_root / project_name
        mount_point = self.run_root / project_name
        
        if not cipher_dir.exists():
            raise Exception(f"Project vault does not exist: {project_name}")
            
        mount_point.mkdir(parents=True, exist_ok=True)
        
        # Check if already mounted
        if os.path.ismount(mount_point):
            console.print(f"[yellow]{project_name} is already mounted.[/yellow]")
            return True, "Already mounted"

        # Use temp file for password
        import tempfile
        passfile_path = None

        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tf:
                tf.write(password)
                passfile_path = tf.name
            os.chmod(passfile_path, 0o600)
            
            cmd = ["gocryptfs", "-q", "-passfile", passfile_path, str(cipher_dir), str(mount_point)]
            
            res = subprocess.run(cmd, capture_output=True, text=True)

            if res.returncode != 0:
                 raise Exception(f"Mount failed: {res.stderr}")
                 
            console.print(f"[green]Mounted {project_name} to {mount_point}[/green]")
            return True, "Mount success"
            
        except Exception as e:
             console.print(f"[red]Mount Error:[/red] {e}")
             return False, str(e)
        finally:
             if passfile_path and os.path.exists(passfile_path):
                 os.unlink(passfile_path)

    def unmount_project(self, project_name):
        """Unmount the project."""
        mount_point = self.run_root / project_name
        
        if not mount_point.exists():
            return True # Logic: if dir doesn't exist, it's not mounted? 
            
        if not os.path.ismount(mount_point):
            # clean up empty dir
            try:
                mount_point.rmdir()
            except:
                pass
            return True
            
        try:
            cmd = ["fusermount", "-u", str(mount_point)]
            subprocess.run(cmd, check=True)
            console.print(f"[green]Unmounted {project_name}[/green]")
            # Cleanup mountpoint dir
            mount_point.rmdir()
            return True
        except Exception as e:
            console.print(f"[red]Unmount failed:[/red] {e}")
            return False
