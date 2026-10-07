"""Hub command line: `python -m hub.cli <command>` (run from the repository root)."""
import argparse
import datetime as dt
import getpass
import ipaddress
import socket
import sys
import time
import uuid
from pathlib import Path


def _hub():
    from hub.app.config import settings
    from hub.app.db import Database
    return settings, Database(settings.data_dir / "hub.db")


def create_admin(args) -> None:
    from hub.app.routes_student import USERNAME
    from hub.app.security import hash_password
    settings, db = _hub()
    username = args.username.strip().lower()
    if not USERNAME.match(username): sys.exit("Usuario inválido (3-40 letras, números, punto, guion).")
    password = args.password or getpass.getpass("Contraseña (mínimo 12 caracteres): ")
    if len(password) < 12: sys.exit("La contraseña de administración debe tener al menos 12 caracteres.")
    existing = db.one("SELECT id FROM users WHERE username=?", (username,))
    if existing:
        db.execute("UPDATE users SET password_hash=?, role='admin', disabled=0 WHERE id=?", (hash_password(password), existing["id"]))
        print(f"Administrador actualizado: {username}")
    else:
        db.execute("INSERT INTO users (id, username, display_name, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
                   (uuid.uuid4().hex, username, username, hash_password(password), "admin", time.time()))
        print(f"Administrador creado: {username}")
    db.audit("admin_cli", "cli", username)


def add_worker(args) -> None:
    from hub.app.security import new_token, token_hash
    _, db = _hub()
    token = new_token()
    if db.one("SELECT id FROM workers WHERE id=?", (args.name,)):
        if not args.rotate: sys.exit(f"El worker {args.name} ya existe. Usá --rotate para generar un token nuevo.")
        db.execute("UPDATE workers SET token_hash=?, disabled=0 WHERE id=?", (token_hash(token), args.name))
    else:
        db.execute("INSERT INTO workers (id, token_hash, created_at) VALUES (?,?,?)", (args.name, token_hash(token), time.time()))
    db.audit("worker_cli", "cli", args.name)
    print(token if args.quiet else f"Worker: {args.name}\nToken (se muestra una sola vez): {token}")


def list_workers(_args) -> None:
    _, db = _hub()
    for row in db.all("SELECT id, disabled, last_seen_at, ip, loaded_model FROM workers ORDER BY id"):
        seen = dt.datetime.fromtimestamp(row["last_seen_at"]).strftime("%Y-%m-%d %H:%M:%S") if row["last_seen_at"] else "nunca"
        print(f"{row['id']:<16} {'deshabilitado' if row['disabled'] else 'habilitado':<14} visto: {seen:<20} ip: {row['ip'] or '-':<16} modelo: {row['loaded_model'] or '-'}")


def make_cert(args) -> None:
    """Self-signed certificate for LAN mode. Prefer a certificate issued by the university when available."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    names = [name.strip() for name in args.hosts.split(",") if name.strip()] or [socket.gethostname()]
    names += ["localhost", "127.0.0.1"]
    alt: list = []
    for name in dict.fromkeys(names):
        try: alt.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError: alt.append(x509.DNSName(name))
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0]), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Local Via")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=args.days))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "hub.key").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (out / "hub.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Certificado: {out / 'hub.crt'}\nClave privada: {out / 'hub.key'}\nNombres válidos: {', '.join(dict.fromkeys(names))}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m hub.cli", description="Administración del hub de Local Via")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin", help="Crea o actualiza una cuenta de administración"); p.add_argument("username"); p.add_argument("--password"); p.set_defaults(func=create_admin)
    p = sub.add_parser("add-worker", help="Registra una PC del laboratorio y muestra su token"); p.add_argument("name"); p.add_argument("--rotate", action="store_true"); p.add_argument("--quiet", action="store_true"); p.set_defaults(func=add_worker)
    p = sub.add_parser("list-workers", help="Lista las PCs registradas"); p.set_defaults(func=list_workers)
    p = sub.add_parser("make-cert", help="Genera un certificado TLS autofirmado para el modo LAN"); p.add_argument("--hosts", default=""); p.add_argument("--days", type=int, default=825); p.add_argument("--out", default="hub/certs"); p.set_defaults(func=make_cert)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
