"""Explicit administrative commands; no automatic default credentials."""
import click
from werkzeug.security import generate_password_hash
from booking import event, write_transaction
from models import Admin, db


def register_commands(app):
    @app.cli.command('admin-account')
    @click.option('--username', prompt='Admin username')
    @click.password_option(confirmation_prompt=True)
    def admin_account(username, password):
        """Create an individual admin, or rotate an existing admin password."""
        username = username.strip()
        if not 1 <= len(username) <= 50 or not 12 <= len(password) <= 128 or password.isspace():
            raise click.ClickException('Username: 1-50 characters; password: 12-128 characters.')
        with write_transaction():
            admin = db.session.scalar(db.select(Admin).where(Admin.username == username))
            if admin is None:
                admin = Admin(username=username, password_hash=generate_password_hash(password))
                db.session.add(admin)
            else:
                admin.password_hash = generate_password_hash(password)
                admin.session_version += 1
            db.session.flush()
            event('server-cli', 'admin_password_set', admin.id)
        click.echo('Admin account updated. Existing sessions are invalidated after rotation.')

    @app.cli.command('import-legacy')
    @click.option('--source', required=True, type=click.Path(exists=True, dir_okay=False))
    @click.option('--output', required=True, type=click.Path(dir_okay=False))
    @click.option('--legacy-timezone', type=click.Choice(['Asia/Seoul', 'UTC']), required=True)
    def import_legacy_command(source, output, legacy_timezone):
        """Read a legacy SQLite backup and produce a separate upgraded database."""
        from legacy_import import import_legacy
        try:
            result = import_legacy(source, output, legacy_timezone)
        except (ValueError, RuntimeError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f'Imported counts: {result}. Source database was not modified.')
