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


def forward(db, twitter_handle, mastodon_handle, debug, number=None, only_mark_as_seen=False):
    t = twitter.Api(**yaml.safe_load(open("conf.yaml")))
    mastodon_creds = "t2m_%s_creds.txt" % mastodon_handle

    if not os.path.exists(mastodon_creds):
        mastodon = Mastodon(client_id='./t2m_clientcred.txt')
        print "Not credentials for mastodon account '%s', creating them (the password will NOT be saved)" % mastodon_handle
        mastodon.log_in(
            argh.io.safe_input("Email for mastodon account '%s': " % mastodon_handle).strip(),
            getpass("Password for mastodon account of '%s': " % mastodon_handle),
            to_file=mastodon_creds
        )

    mastodon = Mastodon(client_id='./t2m_clientcred.txt', access_token=mastodon_creds)

    to_toot = []

    # select tweets first
    for i in reversed(t.GetUserTimeline(screen_name=twitter_handle, count=200)):

        # do not forward retweets for now
        if i.retweeted_status:
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
            text = text.replace(url.url, url.expanded_url)

        if debug:
            print ">>", text
        elif only_mark_as_seen:
            db.setdefault(twitter_handle, {}).setdefault("done", []).append(i.id)
        else:
            to_toot.append(text)

    # slices selected tweets if specified
    if number is not None:
        to_toot = to_toot[:int(number)]

    # actually forward
    if not debug and not only_mark_as_seen:
        for text in to_toot:
            response = mastodon.toot(text)
            assert not response.get("error"), response
            print "[forwarding] >>", text
            time.sleep(30)
            db.setdefault(twitter_handle, {}).setdefault("done", []).append(i.id)

    print "Forwarded %s tweets from %s to %s" % (len(to_toot), twitter_handle, mastodon_handle)

    return db


def one(twitter_handle, mastodon_handle=None, number=None, only_mark_as_seen=False, debug=False):
    db = get_db()

    if mastodon_handle is None and twitter_handle not in db:
        print "Error: I don't have an associated mastodon account for '%s', please provide one to me with -m"
        sys.exit(1)

    if mastodon_handle is None and twitter_handle in db:
        mastodon_handle = db[twitter_handle]["mastodon"]

    # force set new mastodon handle
    db.setdefault(twitter_handle, {})["mastodon"] = mastodon_handle

    db = forward(db, twitter_handle, mastodon_handle, debug=debug, number=number, only_mark_as_seen=only_mark_as_seen)

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

    if not os.path.exists(mastodon_creds):
        mastodon = Mastodon(client_id='./t2m_clientcred.txt')

        print "Grabbing credentials for mastodon handle (password will NOT be stored"
        mastodon.log_in(
            argh.io.safe_input("Email for mastodon account '%s': " % mastodon_handle).strip(),
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
