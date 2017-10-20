# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import os.path as osp
import tempfile
import shutil
import unittest
from contextlib import contextmanager

try:
    # Python >= 3.3
    import unittest.mock as mock
except ImportError:
    import mock

import twitter  # flake8: noqa

import t2m


HERE = osp.abspath(osp.dirname(__file__))


def _fake_tweet(**kwargs):
    kwargs.setdefault('id', 1)
    kwargs.setdefault('retweeted_status', False)
    kwargs.setdefault('quoted_status', False)
    kwargs.setdefault('full_text', 'Tweet %s textual content' % kwargs['id'])
    kwargs.setdefault('urls', [])
    kwargs.setdefault('media', [])
    return mock.Mock(**kwargs)


def _fake_twitter_client(configuration=None):
    fake_client = mock.Mock()
    if configuration is None:
        configuration = {
            'GetUserTimeline.return_value': [
                _fake_tweet(id=id) for id in range(10)],
        }
    if configuration:
        fake_client.configure_mock(**configuration)
    return fake_client


def _media_post(fpath):
    with open(fpath) as fobj:
        return {'id': fobj.read()}


@contextmanager
def _all_mocked(tweets=None):
    if tweets is None:
        tweets = [_fake_tweet(id=id) for id in range(10)]
    conf = {'GetUserTimeline.return_value': tweets}
    with mock.patch('twitter.Api', return_value=_fake_twitter_client(conf)):
        with mock.patch('mastodon.Mastodon.status_post',
                        return_value={}) as status_post:
            with mock.patch('mastodon.Mastodon.media_post',
                            side_effect=_media_post) as media_post:
                yield status_post, media_post


class Twitter2MastodonTC(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        for fname in os.listdir(osp.join(HERE, 'data')):
            shutil.copy(osp.join(HERE, 'data', fname),
                        osp.join(self._tmpdir, fname))
        self._olddir = osp.abspath(os.getcwd())
        os.chdir(self._tmpdir)
        self.new_db()
        self.data_url = 'file://%s/' % osp.join(HERE, 'data')

    def tearDown(self):
        shutil.rmtree(self._tmpdir)
        os.chdir(self._olddir)

    def new_db(self, db=None):
        if db is None:
            db = {
                'tw1': {'mastodon': 'a1@mamot.fr', 'done': [1, 4]},
                'tw2': {'mastodon': 'a2@mamot.fr'},
            }
        t2m._save_db(db, path=osp.join(self._tmpdir, 'db.json'))

    def read_db(self):
        return t2m._get_db(osp.join(self._tmpdir, 'db.json'))

    def test_all(self):
        with _all_mocked() as (status_post, media_post):
            t2m.all(wait_seconds=0)
        self.assertEqual(18, status_post.call_count)
        text = 'Tweet %s textual content'
        self.assertEqual(sorted(  # last call appears first
            ([(text % i,) for i in range(10) if i not in {1, 4}]) +  # tw1
             [(text % i,) for i in range(10)]),                      # tw2
            sorted([args for args, kwargs in status_post.call_args_list]))
        db = self.read_db()
        self.assertEqual(set(range(10)), set(db['tw1']['done']))
        self.assertEqual(set(range(10)), set(db['tw2']['done']))

    def test_one_mark_1(self):
        "Marking tweets as seen adds them to the db"
        with _all_mocked() as (status_post, media_post):
            t2m.one('tw1', only_mark_as_seen=True)
        self.assertEqual(0, status_post.call_count)
        db = self.read_db()
        self.assertEqual(set(range(10)), set(db['tw1']['done']))
        self.assertNotIn('done', db['tw2'])  # check unchanged

    def test_one_mark_2(self):
        "Marking tweets as seen adds the missing ones to the db"
        with _all_mocked():
            t2m.one('tw2', only_mark_as_seen=True)
        db = self.read_db()
        self.assertEqual(set(range(10)), set(db['tw2']['done']))
        self.assertEqual({1, 4}, set(db['tw1']['done']))  # check unchanged

    def test_one_send_4_toots(self):
        self.new_db()
        with _all_mocked() as (status_post, media_post):
            t2m.one('tw1', wait_seconds=0, number=4)
        self.assertEqual(4, status_post.call_count)
        # 1 and 4 were already there and 0, 2, 3, 5 have just been sent:
        self.assertEqual({1, 4, 0, 2, 3, 5},
                         set(self.read_db()['tw1']['done']))

    def test_retweet(self):
        tweet = _fake_tweet(retweeted_status=mock.Mock(
            id='retweeted', full_text='retweeted text', urls=(), media=(),
            user=mock.Mock(screen_name='retweeted_user')),
            )
        with _all_mocked([tweet]) as (status_post, media_post):
            t2m.one('tw2', wait_seconds=0)
            self.assertEqual(0, status_post.call_count)
        with _all_mocked([tweet]) as (status_post, media_post):
            t2m.one('tw2', wait_seconds=0, retweets=True)
        self.assertEqual(1, status_post.call_count)
        args, kwargs = status_post.call_args
        self.assertEqual(
            (u'« retweeted text »\n\n— Retweet '
             u'https://twitter.com/retweeted_user/status/retweeted',), args)

    def test_quoted(self):
        tweet = _fake_tweet(
            full_text='I quote this:',
            quoted_status=mock.Mock(
                id='quoted', full_text='quoted full', urls=(), media=(),
                user=mock.Mock(screen_name='quoted_user')),
        )
        with _all_mocked([tweet]) as (status_post, media_post):
            t2m.one('tw2', wait_seconds=0)
            self.assertEqual(0, status_post.call_count)
        with _all_mocked([tweet]) as (status_post, media_post):
            t2m.one('tw2', wait_seconds=0, retweets=True)
            self.assertEqual(1, status_post.call_count)
        args, kwargs = status_post.call_args
        self.assertEqual(
            (u'I quote this:\n\n« quoted full »\n\n— Retweet '
             u'https://twitter.com/quoted_user/status/quoted',), args)

    def test_private_tweet(self):
        tweet = _fake_tweet(full_text='@private_response')
        with _all_mocked([tweet]) as (status_post, media_post):
            t2m.one('tw2', wait_seconds=0)
        self.assertEqual(0, status_post.call_count)

    def test_complete_tweet(self):
        tweet = _fake_tweet(
            full_text='normal with urls and medias',
            urls=[mock.Mock(url='http://short_url/index.html',
                            expanded_url='http://expanded_url/index.html')],
            media=[mock.Mock(media_url=self.data_url + 'media1.txt'),
                   mock.Mock(media_url=self.data_url + 'media2.txt')]
        )
        with _all_mocked([tweet]) as (status_post, media_post):
            t2m.one('tw2', wait_seconds=0)
            self.assertEqual(1, status_post.call_count)
        args, kwargs = status_post.call_args
        self.assertEqual(('normal with urls and medias',), args)
        self.assertEqual(
            {'media_ids': ['media1 content\n', 'media2 content\n']},
            kwargs)


if __name__ == "__main__":
    unittest.main()
