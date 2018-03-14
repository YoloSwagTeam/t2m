# t2m - Twitter 2 Mastodon

A script to manage the forwarding of tweets from Twitter accounts to a Mastodon one.

# Installation

On debian/ubuntu:

    sudo apt-get install python-virtualenv

    virtualenv ve
    source ve/bin/activate

    # if you run with an old version of python 2.7 (Ubuntu 14.04 for example)
    # you'll need to run those, otherwise requests will break because it won't
    # be able to correctly verify the host of the https issuer
    # if you use python 3 you can ignore that
    pip install pyopenssl ndg-httpsclient pyasn1

    pip install -r requirements.txt

Then you need twitter API credentials. Following this tutorial https://python-twitter.readthedocs.io/en/latest/getting_started.html then create a `conf.yaml` file of this format:

    consumer_key: "..."
    consumer_secret: "..."
    access_token_key: "..."
    access_token_secret: "..."

The credentials for Mastodon are automatically generated at the first startup.

# Python 2/3 and one known bug

Compatible with both.

There is a known bug if you run python2 coming for the STL lib `mimetypes`:
JPEG images will be uploaded with the `.jpe` extension, this will break "going
on the exact url of the image" (will cause a download instead of a display).

This bug is fixed in python 3 so I would recommend running t2m with it.

# Usage

## One account

Forward for one account:

    ./t2m one twitter_account -m mastodon_account

This will forward all not already forwarded tweet (this can be up to 200) while
waiting 30 seconds between each toot. This will also remember the mastodon account (so you don't need to specify it again).

Tweets that starts with a "@" won't be forwarded.  Retweets won't be forwarded unless the `-r` option is specified.

You might want a finer control on your action, so you can do:

    ./t2m one twitter_account -m mastodon_account -n 10

To forward only 10 tweet (be careful: if you relaunch the command this will forward 10 other tweets that weren't already forwarded).

You can also mark the whole available tweet as "already seen" without forwarding them so they'll never be forwarded in the future by using this command:

    ./t2m one twitter_account -m mastodon_account -o

If you want to test your commands without forwarding you can simply uses the `-d` (or `--debug`) option:

    ./t2m one twitter_account -m mastodon_account -d
    ./t2m one twitter_account -m mastodon_account -n 10 -d

## Recommendation

In general, when I had a new account I look at its timeline, read how many tweets make sens then do:

    ./t2m one twitter_account -m mastodon_account -n <number of tweets>
    ./t2m one twitter_account -m mastodon_account -o

## Several accounts

To forward tweets for all accounts, simply run:

    ./t2m all

This is a good command to put inside a crontab.

To check all accounts that will be forwarded, do a:

    ./t2m list

You can also add an account directly without using the `one` command using:

    ./t2m add twitter_account mastodon_account

## Retweets

When enabled, retweets are forwarded using the `retweet.tmpl` file as a template, feel free to edit it to suit your needs.  The following tokens will be replaced in the template:

* `%(text)s`: the retweeted text
* `%(user)s`: the original tweet author username
* `%(id)s`: the original tweet id

To create a link to the original tweet, use `https://twitter.com/%(user)s/status/%(id)s`.  To link to the original author profile, use `https://twitter.com/%(user)s`.


## Content Warnings

Content warnings can be added automatically to toots based on regular
expressions. These are configured by creating a file named cw.json.

For example, simple patterns can be used to match any tweet mentioning specific
keywords:
	{
		"coding": [
			"code", "coding", "pull request", "github", "git", "json", "regex"
		],

		"coffee": [
			"#coffee", "coffee", "caffeine"
		]
	}

If a regex pattern contains a group then that group will be used as the content
warning text. This allows rules such as using the first hashtag of a tweet as
the CW warning:
	{
		"hashtag-prefix": [
			"^(#[^\\s]*)\\s"
		]
	}

This also allows using a prefix such as CW to specify that the first line of a
tweet should be used as the content warning:
	{
		"cw-prefix": [
			"^CW (.*)\\n"
		]
	}

Note that the regex is matched after the `retweet.tmpl` file is applied as a
template, so this can be used to automatically apply a content warning to all
RTs, or RTs from specific people, etc.

# Licence

    Copyright (C) 2017  Laurent Peuch and [Contributors](https://github.com/Psycojoker/t2m/graphs/contributors)

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
