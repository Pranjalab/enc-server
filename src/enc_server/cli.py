import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from enc_server.config import get_enc_dir, load_config, save_config, get_server_url
import requests
import json
from enc_server.enc import EncServer
from enc_server.authentications import Authentication
from enc_server.session import Session


console = Console()
auth = Authentication()

@click.group()
@click.option("--session-id", help="Active session ID for logging.")
@click.pass_context
def cli(ctx, session_id):
    """ENC — Secure, Memory-Only Encryption for Code Execution"""
    ctx.ensure_object(dict)
    ctx.obj["session_id"] = session_id
    # Ensure config dir exists on any command
    get_enc_dir()

def log_result(ctx, result_data):
    """Log the command result to the session file if session_id is provided."""
    from enc_server.session import Session
    sess = Session()
    sess.log_result(ctx, result_data)

def check_server_permission(ctx):
    """Check permissions if running in Server Mode."""
    import os
    import getpass
    
    # We unconditionally check permissions for the server CLI
    # This ensures security even if ENV vars are missing (e.g. non-interactive SSH)


    user = getpass.getuser()
    cmd_path = ctx.command_path.split(" ")[-1] # get leaf command
    
    # Check session for all commands except login
    if cmd_path != "server-login":
        session_id = ctx.obj.get("session_id")
        server = EncServer()
        is_valid, msg = server.verify_session(session_id)
        if not is_valid:
             # Return JSON error for client parsing
             click.echo(json.dumps({"status": "error", "message": f"Session Verification Failed: {msg}"}))
             ctx.exit(1)
             
        # Update session time ONLY if valid
        session = Session() 
        session.update_time(session_id)

    # Check if user exists in policy
    if auth.get_user_role(user) is None:
         console.print(f"[bold red]Access Denied:[/bold red] User '{user}' is not registered. Please contact your admin to add the user.")
         ctx.exit(1)

    if not auth.is_allowed(user, cmd_path):
        error_res = {"status": "error", "message": f"Access Denied: User '{user}' is not allowed to run '{cmd_path}'."}
        click.echo(json.dumps(error_res))
        ctx.exit(1)

def ensure_admin(ctx):
    """Explicitly check if current user is admin."""
    import getpass
    import os
    
    # Unconditional admin check


    user = getpass.getuser()
    role = auth.get_user_role(user)
    
    if role not in [auth.ROLE_SUPER_ADMIN, auth.ROLE_ADMIN]:
        console.print(f"[bold red]Permission Error:[/bold red] Only admins can perform this action.")
        ctx.exit(1)

@cli.command("server-login")
@click.argument("username")
@click.pass_context
def server_login(ctx, username):
    """Internal: Create a session and return JSON."""
    check_server_permission(ctx)
    from enc_server.enc import EncServer
    server = EncServer()
    session = server.create_session(username)
    # Output ONLY JSON for client parsing
    import json
    click.echo(json.dumps(session))

@cli.command("server-logout")
@click.argument("session_id")
@click.pass_context
def server_logout(ctx, session_id):
    """Internal: Destroy a session."""
    check_server_permission(ctx)
    from enc_server.enc import EncServer
    server = EncServer()
    server.logout_session(session_id)
    click.echo(json.dumps({"status": "logged_out"}))


@cli.command("server-project-init")
@click.argument("project_name")
@click.option("--password", default=None, help="Project encryption password (if not provided, will prompt)")
@click.option("--project-dir", default=None, help="Local project directory on client (for tracking)")
@click.pass_context
def server_project_init(ctx, project_name, password, project_dir):
    """Internal: Initialize encrypted project vault."""
    check_server_permission(ctx)
    
    # Handle password prompt if not provided
    if not password:
         password = click.prompt("Enter Project Password", hide_input=True)
         
    import getpass
    import json
    user = getpass.getuser()
    session_id = ctx.obj.get("session_id")
    
    server = EncServer()
    success, res = server.project_init(project_name, password, session_id, project_dir)
    
    log_result(ctx, res)
    click.echo(json.dumps(res))

@cli.command("server-project-mount")
@click.argument("project_name")
@click.option("--password", prompt=True, hide_input=True)
@click.pass_context
def server_project_mount(ctx, project_name, password):
    """Internal: Mount encrypted project."""
    check_server_permission(ctx)
    
    server = EncServer()
    success, res = server.project_mount(project_name, password, ctx.obj.get("session_id"))
    click.echo(json.dumps(res))

@cli.command("server-project-remove")
@click.argument("project_name")
@click.pass_context
def server_project_remove(ctx, project_name):
    """Remove a project securely."""
    check_server_permission(ctx)
    server = EncServer()
    success, res = server.remove_project(project_name, ctx.obj.get("session_id"))
    click.echo(json.dumps(res))

@cli.command("server-project-list")
@click.pass_context
def server_project_list(ctx):
    """Internal: List projects for the current user."""
    check_server_permission(ctx)
    
    server = EncServer()
    success, res = server.project_list(ctx.obj.get("session_id"))
    
    # log_result(ctx, res) # Optional, depends on if we want to log every list op
    click.echo(json.dumps(res))

@cli.command("server-project-unmount")
@click.argument("project_name")
@click.pass_context
def server_project_unmount(ctx, project_name):
    """Internal: Unmount project."""
    check_server_permission(ctx)
    
    server = EncServer()
    success, res = server.project_unmount(project_name, ctx.obj.get("session_id"))
    click.echo(json.dumps(res))



@cli.command("server-project-run")
@click.argument("project_name")
@click.argument("cmd_str")
@click.pass_context
def server_project_run(ctx, project_name, cmd_str):
    """Internal: Run a command in project vault."""
    check_server_permission(ctx)
    
    server = EncServer()
    success, res = server.project_run(project_name, cmd_str, ctx.obj.get("session_id"))
    click.echo(res)

@cli.command("server-project-sync")
@click.argument("project_name")
@click.argument("sync_summary")
@click.pass_context
def server_project_sync(ctx, project_name, sync_summary):
    """Internal: Log a sync operation."""
    check_server_permission(ctx)
    # Sync is handled by rsync, but we can log the fact it happened and its summary
    log_result(ctx, sync_summary)
    click.echo(json.dumps({"status": "success"}))

@cli.group()
def project():
    """Manage ENC projects."""
    pass

@project.command("list")
@click.pass_context
def list_projects(ctx):
    """List projects accessible to the current user."""
    check_server_permission(ctx)
    import getpass
    from rich.table import Table
    
    user = getpass.getuser()
    server = EncServer()
    projects = server.get_user_projects(user)
    
    table = Table(title=f"Accessible Projects for {user}")
    table.add_column("Project Name", style="green")
    
    if "*" in projects:
        table.add_row("[bold goldenrod]ALL PROJECTS (Admin)[/bold goldenrod]")
    else:
        for p in projects:
            table.add_row(p)
            
    console.print(table)

@cli.command("server-setup-ssh-key")
@click.option("--key", required=True, help="Public SSH key content")
@click.pass_context
def server_setup_ssh_key(ctx, key):
    """Internal: Add public SSH key to the current user."""
    check_server_permission(ctx)
    import getpass
    import json
    
    # Identify user from system (since they are logged in via SSH/Session)
    user = getpass.getuser()
    
    server = EncServer()
    success, res = server.add_ssh_key(user, key)
    
    log_result(ctx, res)
    click.echo(json.dumps(res))

@cli.group()
def user():
    """Manage ENC users."""
    pass

@user.command("create")
@click.argument("username", required=False)
@click.option("--password", help="User password")
@click.option("--role", type=click.Choice([auth.ROLE_ADMIN, auth.ROLE_DEV]), help="User role")
@click.option("--ssh-key", help="SSH Public Key")
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format")
@click.pass_context
def user_create(ctx, username, password, role, ssh_key, json_output):
    """Create a new user."""
    # Check permissions
    check_server_permission(ctx)
    ensure_admin(ctx)
    
    # Interactive mode if not json and missing args
    if not json_output and not all([username, password, role]):
        if not username:
            username = Prompt.ask("Username")
        console.print(f"[bold]Creating user: {username}[/bold]")
        if not role:
            role = Prompt.ask("Role", choices=[auth.ROLE_ADMIN, auth.ROLE_DEV], default=auth.ROLE_DEV)
        if not password:
             password = Prompt.ask("Password", password=True)
        if not ssh_key:
             ssh_key = Prompt.ask("SSH Public Key (optional)", default="")
             if ssh_key == "": ssh_key = None

    if not username or not password:
        if json_output:
             res = {"status": "error", "message": "Missing username or password"}
             log_result(ctx, res)
             click.echo(json.dumps(res))
             ctx.exit(1)
        else:
             console.print("[red]Username and password are required.[/red]")
             ctx.exit(1)

    # Use EncServer logic
    server = EncServer()
    if server.create_user(username, password, role or "user", ssh_key):
        if json_output:
            res = {"status": "success", "username": username}
            log_result(ctx, res)
            click.echo(json.dumps(res))
        else:
            console.print(f"[bold green]Success:[/bold green] User '{username}' created.")
    else:
        if json_output:
             res = {"status": "error", "message": "Failed to create user"}
             log_result(ctx, res)
             click.echo(json.dumps(res))
        else:
             console.print(f"[bold red]Failed to create user.[/bold red]")

@user.command("list")
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format")
@click.pass_context
def user_list(ctx, json_output):
    """List all managed users."""
    check_server_permission(ctx)
    ensure_admin(ctx)
    from rich.table import Table

    try:
        server = EncServer()
        res = server.get_all_users(ctx.obj.get("session_id") if json_output else None)

        if json_output:
             click.echo(json.dumps(res))
             return

        table = Table(title="ENC Users")
        table.add_column("Username", style="cyan")
        table.add_column("Role", style="magenta")
        table.add_column("Permissions")

        for user_entry in res.get("users", []):
            username = user_entry.get("username")
            role = user_entry.get("role")
            perms = ", ".join(user_entry.get("permissions", []))
            table.add_row(username, role, perms)
            
        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@user.command("remove")
@click.argument("username", required=False)
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format")
@click.pass_context
def user_remove(ctx, username, json_output):
    """Remove a restricted user."""
    check_server_permission(ctx)
    ensure_admin(ctx)
    
    if not username:
        if json_output:
             res = {"status": "error", "message": "Missing username"}
             log_result(ctx, res)
             click.echo(json.dumps(res))
             ctx.exit(1)
        else:
             username = Prompt.ask("Username to remove")

    if username == "admin":
        if json_output:
             res = {"status": "error", "message": "Cannot remove admin user"}
             log_result(ctx, res)
             click.echo(json.dumps(res))
             ctx.exit(1)
        else:
             console.print("[bold red]Cannot remove admin user.[/bold red]")
             ctx.exit(1)

    if not json_output:
        console.print(f"[bold red]Removing user: {username}[/bold red]")
    
    server = EncServer()
    if server.delete_user(username):
        if json_output:
            res = {"status": "success", "username": username}
            log_result(ctx, res)
            click.echo(json.dumps(res))
        else:
            console.print(f"[bold green]Success:[/bold green] User '{username}' removed.")
    else:
        if json_output:
             res = {"status": "error", "message": "Failed to delete user"}
             log_result(ctx, res)
             click.echo(json.dumps(res))
        else:
             console.print(f"[bold yellow]Warning:[/bold yellow] System user might not exist or failed to remove.")

@cli.command()
@click.pass_context
def status(ctx):
    """Show the current security status."""
    check_server_permission(ctx)
    res = "System Locked"
    log_result(ctx, {"status": res})
    console.print(Panel(res, title="ENC Status", style="red"))



def main():
    cli()
