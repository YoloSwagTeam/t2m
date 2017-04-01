import os
import sys
import json
import time

from getpass import getpass

import yaml
import argh
import twitter

from mastodon import Mastodon


def get_db():
    if os.path.exists("db.json"):
        return json.load(open("db.json", "r"))

    return {}


def save_db(db):
    json.dump(db, open("db.json", "w"), indent=4)


def forward(db, twitter_handle, mastodon_handle, debug):
    t = twitter.Api(**yaml.safe_load(open("conf.yaml")))
    mastodon_creds = "t2m_%s_creds.txt" % mastodon_handle

    if not os.path.exists(mastodon_creds):
        mastodon = Mastodon(client_id='./t2m_clientcred.txt')
        print "Not credentials for mastodon account '%s', creating them (the password will NOT be saved)" % mastodon_handle
        mastodon.log_in(
            input("Email for mastodon account '%s': " % mastodon_handle).strip(),
            getpass("Password for mastodon account of '%s': " % mastodon_handle),
            to_file=mastodon_creds
        )

    mastodon = Mastodon(client_id=mastodon_creds)

    for i in t.GetUserTimeline(screen_name=twitter_handle, count=200):

        # do not forward retweets for now
        if i.retweeted:
            continue

        # do not forward pseudo-private answer for now
        if i.text.startswith("@"):
            continue

        # do not forward already forwarded tweets
        if i.id in db.get(twitter_handle, []):
            continue

        text = i.text

        # remove this t.co crap
        for url in i.urls:
            text.replace(url.url, url.expanded_url)

        i.text

        if debug:
            print ">>", i.text
        else:
            mastodon.toot('Tooting from python!')
            time.sleep(30)
            db.setdefault(twitter_handle, {}).setdefault("done", []).append(i.id)

    return db


def one(twitter_handle, mastodon_handle=None, debug=False):
    db = get_db()

    if mastodon_handle is None and twitter_handle not in db:
        print "Error: I don't have an associated mastodon account for '%s', please provide one to me with -m"
        sys.exit(1)

    if mastodon_handle is None and twitter_handle in db:
        mastodon_handle = db[twitter_handle]["mastodon"]

    # force set new mastodon handle
    db.setdefault(twitter_handle, {})["mastodon"] = mastodon_handle

    db = forward(db, twitter_handle, mastodon_handle, debug)

    save_db(db)



def all(debug=False):
    db = get_db()

    for twitter_handle in db:
        if not db[twitter_handle].get("mastodon"):
            print "WARNING: not mastodon handle for twitter account '%s', add one using 't2m add' command" % (twitter_handle)
            continue

        db = forward(db, twitter_handle, db[twitter_handle]["mastodon"], debug)

    save_db(db)


def add(twitter_handle, mastodon_handle):
    db = get_db()

    mastodon_creds = "t2m_%s_creds.txt" % mastodon_handle

    mastodon = Mastodon(client_id='./t2m_clientcred.txt')

    if not os.path.exists(mastodon_creds):
        print "Grabbing credentials for mastodon handle (password will NOT be stored"
        mastodon.log_in(
            input("Email for mastodon account '%s': " % mastodon_handle).strip(),
            getpass("Password for mastodon account of '%s': " % mastodon_handle),
            to_file=mastodon_creds
        )

    db[twitter_handle] = {
        "mastodon": mastodon_handle
    }

    save_db(db)
    print "done"


parser = argh.ArghParser()
parser.add_commands([one, all, add])

if __name__ == '__main__':
    parser.dispatch()
