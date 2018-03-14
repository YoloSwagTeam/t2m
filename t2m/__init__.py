from __future__ import print_function

import os.path as osp
import sys
import json
import time
import shutil
import tempfile
import codecs
import re

try:
    from urllib import urlretrieve
except ImportError:
    from urllib.request import urlretrieve

from getpass import getpass

import yaml
import argh
import twitter

from mastodon import Mastodon

try:
    from HTMLParser import HTMLParser
except ImportError:
    from html.parser import HTMLParser


HERE = osp.abspath(osp.dirname(__file__))

ENDS_WITH_TCO_URL_REGEX = re.compile(
    '.*(?P<stripme> https://t\.co/[^/ ]{10})$')


def _get_content_warnings_db():
    if os.path.exists("cw.json"):
        return json.load(open("cw.json", "r"))

    return {}


def _get_db(path="db.json"):
    """Return the database content from `path` (defaults to "db.json").

    It is stored on disk in the json format and as the following
    model:

    {
        <twitter handle>: {
            "mastodon": <mastodon complete handle>,
            "done": [<list of tweet ids (integers)>]
        }
    }

    """
    if osp.isfile(path):
        with open(path) as fobj:
            return json.load(fobj)
    return {}


def _save_db(db, path="db.json"):
    """Save given `db` python structure to a json file at `path` (defaults
    to "db.json")

    """
    with open(path, "w") as fobj:
        json.dump(db, fobj, indent=4)


def _ensure_client_exists_for_instance(instance):
    "Create the client creds file if it does not exist, and return its path."
    client_id = "t2m_%s_clientcred.txt" % instance
    if not osp.exists(client_id):
        Mastodon.create_app('t2m', to_file=client_id,
                            api_base_url='https://%s' % instance,
                            )
    return client_id


def _find_potential_content_warning(toot_text):
    "Based on cw.json, find a potential automatic content warning based on the toot content."
    warning = None

    for content_warning in _get_content_warnings_db():
        for pattern in content_warnings[content_warning]:
            match = re.search(pattern=pattern, string=t)
            if not match:
                continue

            # If there is a group in the re then use it
            if match.groups():
                warning = match.group(1)
                toot_text = re.sub(pattern, "", toot_text)

            else:
                # If no group then use the key from the json
                warning = content_warning

            # once we get our first content warning, stop
            return warning, toot_text

    return warning, toot_text


def _check_complete_mastodon_handle(mastodon_handle, twitter_handle):
    """Print an error and exit if the given mastodon handle does not contain
    the instance name.

    The `twitter_handle` parameter is also required to display a user-
    understandable message.

    """
    if "@" not in mastodon_handle:
        msg = ("ERROR: multiple instances are now handled, but your mastodon"
               " handle %(mastodon)r needs the instance name. Please add it"
               " using:\n%(exe)s add %(twitter)s %(mastodon)s@theinstance.com")
        ctx = {"exe": sys.argv[0],
               "twitter": twitter_handle,
               "mastodon": mastodon_handle}
        print(msg % ctx, file=sys.stderr)
        sys.exit(1)


def _collect_toots(twitter_client, twitter_handle, done=(), retweets=False,
                   max_tweets=200, strip_trailing_url=False):
    """Return a list of dicts describing toots to be sent.

    Given `twitter_handle` and the `done` list of already sent tweet
    ids (defaults to the empty list), `twitter_client` is used to
    fetch tweets' textual content and medias. The last `max_tweets` are
    fetched (defaults to 200), and retweets are ignored unless the
    `retweets` parameter is set to a truthy value.

    An item of the return list as the following model:

    {
        "text": <the textual content of the tweet>,
        "id": <the original tweet id>,
        "medias": <the list of attached media URLs (t.co URLs are expanded)>
    }

    """
    toots = []

    if retweets:
        with codecs.open(osp.join(HERE, "retweet.tmpl"),
                         encoding="utf-8") as fobj:
            retweet_template = fobj.read()

    h = HTMLParser()

    # "i" is a status http://python-twitter.readthedocs.io/en/latest/_modules/twitter/models.html#Status
    for i in reversed(twitter_client.GetUserTimeline(
            screen_name=twitter_handle, count=max_tweets)):

        retweeted_status = i.retweeted_status or i.quoted_status

        if retweeted_status:
            if retweets:
                text = retweet_template % {
                    "text": retweeted_status.full_text,
                    "user": retweeted_status.user.screen_name,
                    "id": retweeted_status.id
                }

                # can only be greater than 500 chars if it's a quoted tweet so checking here
                # delete the text of the quoted tweet from the toot end replace it with a much shorter string
                if i.quoted_status and len(text) > 500:
                    text = retweet_template % {
                        "text": "Quoted tweet's link below",
                        "user": retweeted_status.user.screen_name,
                        "id": retweeted_status.id
                    }
                    text = i.full_text + "\n\n" + text

                if i.quoted_status:
                    text = i.full_text + "\n\n" + text

                urls = retweeted_status.urls
                media = retweeted_status.media
            else:
                continue
        else:
            # do not forward pseudo-private answer for now
            if i.full_text.startswith("@"):
                continue

            text = i.full_text
            urls = i.urls
            media = i.media

        # do not forward already forwarded tweets
        if i.id in done:
            continue

        # remove this t.co crap
        for url in urls:
            text = text.replace(url.url, url.expanded_url)

        # strip last t.co URL, which is a reference to the tweet
        # itself (other URLs were expanded above, so there is no risk
        # to remove an important, part of the text, URL)
        if strip_trailing_url:
            match = ENDS_WITH_TCO_URL_REGEX.search(text)
            if match is not None:
                text = text[:-len(match.group('stripme'))]

        toot_text = h.unescape(text)
        warning, toot_text = _find_potential_content_warning(toot_text)

        toots.append({
            "text": toot_text,
            "content_warning": warning,
            "id": i.id,
            "medias": [x.media_url for x in media] if media else []
        })

    return toots


def _send_toot(mastodon, toot):
    """Send a toot given its description in the `toot` parameter.

    See the `_collect_toots` function for the expected description
    format.

    This function fetches all media URLs of `toot` in a temporary
    directory (removed afterwards) and uses the given Mastodon client
    `mastodon` to send them along with the toot's textual content.

    It may raise an AssertionError if the client does not succeed to
    send to given toot.

    """
    tmp_dir = tempfile.mkdtemp()
    try:
        medias = []
        for number, media_url in enumerate(toot["medias"]):
            dl_file_path = osp.join(tmp_dir, str(number) + "."
                                    + media_url.split(".")[-1])
            urlretrieve(media_url, dl_file_path)
            medias.append(mastodon.media_post(dl_file_path)["id"])

        response = mastodon.status_post(toot["text"],
                                        media_ids=medias,
                                        spoiler_text=toot["content_warning"])
        assert not response.get("error"), response
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _get_mastodon_client(mastodon_handle):
    " Return a Mastodon client for the given handle. "
    instance = mastodon_handle.split("@", 1)[1]

    client_id, access_token = _login_to_mastodon(mastodon_handle)

    return Mastodon(client_id=client_id,
                    access_token=access_token,
                    api_base_url='https://%s' % instance)


def _forward(db, twitter_handle, mastodon_handle, number=None,
             only_mark_as_seen=False, retweets=False, debug=False,
             wait_seconds=30, strip_trailing_url=False):
    """Internal function that does the actual tweet forwarding job.

    This function modifies the given `db` parameter.

    See the `one` function doc for more information about its
    parameters.

    The `wait_seconds` parameter is the time between we wait between
    two sendings.

    """
    with open("conf.yaml") as fobj:
        twitter_client = twitter.Api(
            tweet_mode='extended', **yaml.safe_load(fobj))

    done = db.setdefault(twitter_handle, {}).setdefault("done", [])

    to_toot = _collect_toots(twitter_client, twitter_handle,
                             done=done, retweets=retweets,
                             strip_trailing_url=strip_trailing_url)
    if only_mark_as_seen:
        done.extend([t["id"] for t in to_toot])
        print("Marked all available tweets as seen (%s tweets marked)"
              % len(to_toot))
        return

    # slices selected tweets if specified
    if number is not None:
        to_toot = to_toot[-int(number):]

    # actually forward
    forwarded = 0
    _check_complete_mastodon_handle(mastodon_handle, twitter_handle)
    mastodon = _get_mastodon_client(mastodon_handle)

    for num, toot in enumerate(to_toot):
        if debug:
            print(">>", toot["text"].encode("utf-8"),
                  " ".join(toot["medias"]))
            continue
        if wait_seconds and num > 0:
            time.sleep(wait_seconds)
        try:
            _send_toot(mastodon, toot)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("ERROR: could not forward the tweet [%s] '%s' "
                  "because '%s', skipping for now"
                  % (toot["id"], toot["text"], e), file=sys.stderr)
            continue

        forwarded += 1
        print("[forwarding] >>",
              toot["text"].encode("utf-8"),
              " ".join(toot["medias"]))
        done.append(toot["id"])
        _save_db(db)

    if not to_toot:
        print("Nothing to do for %s" % twitter_handle)
    else:
        print("Forwarded %s tweets from %s to %s"
              % (forwarded, twitter_handle, mastodon_handle))

    return


def one(twitter_handle, mastodon_handle=None, number=None,
        only_mark_as_seen=False, retweets=False, debug=False,
        wait_seconds=30, strip_trailing_url=False):
    """Forward tweets of *one* twitter account to Mastodon.

    If the `mastodon_handle` parameter is not specified, the given
    `twitter_handle` must be present in the database, and the
    corresponding Mastodon account is used.

    When the `number` parameter is passed, it is used as the maximum
    number of tweets to be forwarded at once. Note the last tweets are
    kept, not the first.

    If `only_mark_as_seen` is set to True (default is False), then the
    selected tweets not actually forwarded but marked as if they had
    already been.

    If `retweets` is set to True (default is False), also the retweets
    (and quotes) will be forwarded.

    If `strip_trailing_url` is True, the https://t.co/... at the end
    of some tweets is removed. Note that all other t.co shortened URLs
    identified by Twitter and are expanded beforehand, so there should
    be no risk to remove an URL that was part of the tweet when
    activating this option.

    The `debug` parameter, if set, is used to display what tweets
    would be forwarded if unset (the default), but does not actually
    forward any tweet.

    """

    db = _get_db()

    if mastodon_handle is None:
        if twitter_handle not in db:
            print("ERROR: No associated mastodon account for twitter account"
                  " %r. Use the '-m' option to provide one." % twitter_handle,
                  file=sys.stderr)
            sys.exit(1)
        else:
            mastodon_handle = db[twitter_handle]["mastodon"]

    _check_complete_mastodon_handle(mastodon_handle, twitter_handle)

    # force set new mastodon handle
    db.setdefault(twitter_handle, {})["mastodon"] = mastodon_handle

    _forward(db, twitter_handle, mastodon_handle, number=number,
             only_mark_as_seen=only_mark_as_seen, retweets=retweets,
             debug=debug, wait_seconds=wait_seconds,
             strip_trailing_url=strip_trailing_url)

    _save_db(db)


def all(retweets=False, debug=False, wait_seconds=30,
        strip_trailing_url=False):
    """Forward the tweets of all known twitter accounts to Mastodon.

    Only not already forwarded tweets are forwarded. Note that you
    must preserve your "db.json" file as this is where the list of
    already forwarded tweets is stored: no comparison between Twitter
    and Mastodon posts is performed to determine the posts to be
    forwarded, only the database. Use `t2m forward -o` to avoid
    forwarding old tweets, by marking them already forwarded.

    When optional `retweets` parameter is True (it is False by
    default), the retweets are also forwarded to Mastodon.

    """
    db = _get_db()

    for twitter_handle in db:
        if not db[twitter_handle].get("mastodon"):
            print("WARNING: no mastodon handle for twitter account %r, "
                  "add one using the 't2m add' command. Skipped."
                  % twitter_handle)
            continue

        _forward(db, twitter_handle, db[twitter_handle]["mastodon"],
                 retweets=retweets, debug=debug, wait_seconds=wait_seconds,
                 strip_trailing_url=strip_trailing_url)

    _save_db(db)


def _login_to_mastodon(mastodon_handle):
    """Login to given Mastodon account, returning client id and access token.

    The client id file for this Mastodon account must pre-exist (named
    "t2m_<mastodon_handle>_creds.txt").

    The access token file (named "t2m_<mastodon_handle>_creds.txt") is written.
    after the Mastodon email and password are interactively input.
    """
    instance = mastodon_handle.split("@", 1)[1]
    client_id = _ensure_client_exists_for_instance(instance)
    access_token = "t2m_%s_creds.txt" % mastodon_handle
    if not osp.exists(access_token):
        mastodon = Mastodon(client_id=client_id,
                            api_base_url="https://%s" % instance)

        print("No credential file found for mastodon account %r, "
              "creating it (the password will NOT be saved)" % mastodon_handle)
        mastodon.log_in(
            argh.io.safe_input(
                "Email for mastodon account %r: " % mastodon_handle).strip(),
            getpass("Password for mastodon account of '%s' (won't be stored): "
                    % mastodon_handle),
            to_file=access_token,
        )
    return client_id, access_token


def add(twitter_handle, mastodon_handle):
    "Add the link between given twitter and mastodon handles in the database."
    db = _get_db()

    _check_complete_mastodon_handle(mastodon_handle, twitter_handle)

    # retrocompatibility
    access_token = "t2m_%s_creds.txt" % mastodon_handle
    if osp.exists("t2m_%s_creds.txt" % mastodon_handle.split("@")[0]):
        shutil.move("t2m_%s_creds.txt" % mastodon_handle.split("@")[0],
                    access_token)

    _login_to_mastodon(mastodon_handle)

    db.setdefault(twitter_handle, {})["mastodon"] = mastodon_handle

    _save_db(db)
    print("done")


def list():
    "List known twitter accounts, which tweets can be forwarded to Mastodon."
    db = _get_db()
    for i in db:
        print(" *", i)


def main():
    if not osp.exists("conf.yaml"):
        print("You need to have a conf.yaml file containing twitter connection"
              " informations, please read the documentation"
              " https://github.com/Psycojoker/t2m#installation")
        sys.exit(1)

    parser = argh.ArghParser()
    parser.add_commands([one, all, add, list])
    parser.dispatch()


if __name__ == '__main__':
    main()
