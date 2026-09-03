#!/usr/bin/env python3
"""Local recovery utility for the initial administrator password."""
import getpass
import argparse
import secrets
import sqlite3
import subprocess

from server import DB, hp


def copy_to_clipboard(value):
    subprocess.run(['clip.exe'], input=value.encode('utf-8'), check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--generate', action='store_true', help='Generate and copy a recovery password to the clipboard.')
    args = parser.parse_args()
    if args.generate:
        password = secrets.token_urlsafe(18)
        try:
            copy_to_clipboard(password)
        except Exception as error:
            raise SystemExit('Could not copy the generated password to the clipboard: ' + str(error))
    else:
        password = getpass.getpass('New admin password (12 characters minimum): ')
        confirmation = getpass.getpass('Confirm new admin password: ')
        if password != confirmation:
            raise SystemExit('Passwords do not match.')
    if len(password) < 12:
        raise SystemExit('Password must be at least 12 characters long.')
    connection = sqlite3.connect(DB)
    try:
        updated = connection.execute(
            "update users set password_hash=? where username='admin'", (hp(password),)
        ).rowcount
        if updated != 1:
            raise SystemExit('The admin account was not found.')
        connection.commit()
    finally:
        connection.close()
    if args.generate:
        print('Admin password updated and copied to the clipboard. Paste it once into the sign-in form, then save it in a password manager.')
    else:
        print('Admin password updated. Start the server and sign in again.')


if __name__ == '__main__':
    main()
