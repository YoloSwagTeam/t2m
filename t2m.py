import os
import sys
import json
import time

import yaml
import twitter
from mastodon import Mastodon


def main():
    if os.path.exists("db.json"):
        db = json.load(open("db.json", "r"))
    else:
        db = {}

    twitter_handle = sys.argv[1]
    mastodon_handle = sys.argv[2]

    t = twitter.Api(**yaml.safe_load(open("conf.yaml")))
    mastodon = Mastodon(client_id = "t2m_%s_creds.txt" % mastodon_handle)

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

        # mastodon.toot('Tooting from python!')
        print ">>", i.text
        time.sleep(30)

        db.setdefault(twitter_handle, []).append(i.id)

    json.dump(db, open("db.json", "w"), indent=4)


if __name__ == '__main__':
    main()
