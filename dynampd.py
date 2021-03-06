#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
#                     Version 2, December 2004
#
#  Copyright (C) 2004 Sam Hocevar <sam@hocevar.net>
#  Everyone is permitted to copy and distribute verbatim or modified
#  copies of this license document, and changing it is allowed as long
#  as the name is changed.
#
#             DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
#    TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION
#
#   0. You just DO WHAT THE FUCK YOU WANT TO.
#

import mpd, time, urllib, re, random, json

__author__  = 'ubitux and Amak'
__version__ = '1.1.0'

class DynaMPD:

    _api_key      = 'b25b959554ed76058ac220b7b2e0a026'
    _api_root_url = 'http://ws.audioscrobbler.com/2.0/'
    _sim_scores   = {'title': 4, 'artist': 1}

    def __init__(self, mpd_client):
        self.mpd_client = mpd_client
        self.max_selection_len = mpd_client.max_songs

    def get_a_selection(self, playing_artist, playing_track):

        def sel_ok(selection):
            self._log('')
            return selection

        playlist  = self.mpd_client.playlist()
        selection = []

        if isinstance(playing_artist, list):
            playing_artist = ', '.join(playing_artist)
        splitted_artists = list(set([playing_artist] + [a.strip() for a in re.split(r'(?i),|feat[^ ]*|&|;', playing_artist)]))
        random.shuffle(splitted_artists)

        self._log(':: Search similar track [%s - %s]' % (playing_artist, playing_track))

        # Check for similar songs
        doc = self._api_request({'method': 'track.getsimilar', 'artist': playing_artist, 'track': self._cleanup_track_title(playing_track)})
        similartracks = doc.get('similartracks', {}).get('track')
        if isinstance(similartracks, list):
            for node in similartracks:
                artist = node.get('artist', {}).get('name').encode('utf-8', 'replace')
                title  = node.get('name').encode('utf-8', 'replace')
                if None in (title, artist):
                    continue
                songs = self.mpd_client.search('artist', artist, 'title', title)
                if self._add_one_song_to_selection(songs, playlist, selection) >= self.max_selection_len:
                    return sel_ok(selection)

        # Check for top songs of similar artists
        for sub_artist in splitted_artists:
            doc = self._api_request({'method': 'artist.getsimilar', 'artist': sub_artist})
            similarartists = doc.get('similarartists', {}).get('artist')
            if not isinstance(similarartists, list):
                continue
            for node in similarartists:
                artist = node.get('name').encode('utf-8', 'replace')
                if not self.mpd_client.search('artist', artist):
                    self._log('No artist matching [%s] in database' % artist)
                    continue
                doc_toptracks = self._api_request({'method': 'artist.getTopTracks', 'artist': artist, 'limit': 20})
                toptracks = doc_toptracks.get('toptracks', {}).get('track')
                if not isinstance(toptracks, list) or not toptracks:
                    continue
                random.shuffle(toptracks)
                for toptrack in toptracks:
                    title = toptrack.get('name').encode('utf-8', 'replace')
                    songs = self.mpd_client.search('artist', artist, 'title', title)
                    if self._add_one_song_to_selection(songs, playlist, selection) >= self.max_selection_len:
                        return sel_ok(selection)

        return sel_ok(selection)

    def _cleanup_track_title(self, title):
        return re.sub(r'\([^)]*\)', '', title).strip().lower()

    def _get_similitude_score(self, artist, title):

        def simplify_artists(artist):
            return ', '.join((a.lower() for a in artist)) if isinstance(artist, list) else artist.lower()

        artist = simplify_artists(artist)
        title  = self._cleanup_track_title(title)
        plinfo = self.mpd_client.playlistinfo()
        sim = 0
        for song in plinfo:
            if not 'artist' in song or not 'title' in song:
                continue
            tmp_artist = simplify_artists(song['artist'])
            tmp_title  = self._cleanup_track_title(song['title'])
            if tmp_artist in artist or artist in tmp_artist:
                sim += self._sim_scores['artist']
            if title in tmp_title or tmp_title in title:
                sim += self._sim_scores['title']
        return sim

    def _add_one_song_to_selection(self, songs, playlist, selection):
        if not songs:
            return len(selection)
        for song in songs:
            artist = song.get('artist')
            title  = song.get('title')
            fname  = song['file']
            fullpl = playlist + selection
            if not artist or not title or 'file: %s' % fname in fullpl or fname in fullpl:
                continue
            score     = self._get_similitude_score(artist, title)
            min_score = sum(self._sim_scores.values())
            max_score = min_score * 3
            if score > random.randint(min_score, max_score):
                continue
            self._log('    → %s' % fname)
            selection.append(fname)
            break
        return len(selection)

    def _api_request(self, data):
        url = '%s?api_key=%s&format=json&%s' % (self._api_root_url, self._api_key, urllib.urlencode(data))
        self._log('   [LastFM] request: %s | url: %s' % (data['method'], url))
        return json.load(urllib.urlopen(url))

    def _log(self, msg):
        if self.mpd_client.verbose:
            print msg

class Core(mpd.MPDClient):

    def __init__(self):
        import os, optparse, ConfigParser
        from StringIO import StringIO

        mpd.MPDClient.__init__(self)

        env_host = os.environ.get('MPD_HOST', 'localhost')
        if '@' in env_host:
            env_pass, env_host = env_host.split('@', 1)
        else:
            env_pass = None

        env_port = os.environ.get('MPD_PORT', None)
        try:
            env_port = int(env_port)
        except (TypeError, ValueError):
            env_port = 6600

        config = ConfigParser.RawConfigParser()
        try:
            fname = os.path.join(os.environ.get('XDG_CONFIG_HOME', '~/.config'), 'dynampd.conf')
            cfile = open(os.path.expanduser(fname), 'r')
            config.readfp(StringIO('[s]\n' + cfile.read()))
        except IOError:
            cfile = None
        cfg_host  = config.get('s', 'host')         if config.has_option('s', 'host')       else env_host
        cfg_pass  = config.get('s', 'password')     if config.has_option('s', 'password')   else env_pass
        cfg_port  = config.getint('s', 'port')      if config.has_option('s', 'port')       else env_port
        cfg_quiet = config.getboolean('s', 'quiet') if config.has_option('s', 'quiet')      else False
        cfg_msong = config.getint('s', 'max_songs') if config.has_option('s', 'max_songs')  else 3
        cfg_wait  = config.getint('s', 'wait')      if config.has_option('s', 'wait')       else 20
        if cfile:
            cfile.close()

        parser = optparse.OptionParser()
        parser.add_option('-a', '--host', dest='host', help='MPD host', default=cfg_host)
        parser.add_option('-n', '--password', dest='password', help='MPD password', default=cfg_pass)
        parser.add_option('-p', '--port', dest='port', type='int', help='MPD port', default=cfg_port)
        parser.add_option('-q', '--quiet', dest='verbose', action="store_false", help='Quiet mode', default=(not cfg_quiet))
        parser.add_option('-m', '--max-songs', dest='max_songs', type='int', help='Maximum songs to append each time', default=cfg_msong)
        parser.add_option('-w', '--wait', dest='wait', type='int', help='Percent of current song length to wait before requesting new songs', default=cfg_wait)
        opts, _ = parser.parse_args()

        self.verbose   = opts.verbose
        self.max_songs = opts.max_songs
        self.wait      = opts.wait
        self.connect(opts.host, opts.port)
        if opts.password:
            self.password(opts.password)

    def run(self):

        def is_worth_listening(elapsed_time, total_time):
            return (total_time - elapsed_time) < int(total_time * (100 - self.wait) / 100.)

        prev = (None, None)
        dynampd = DynaMPD(self)
        try:
            while True:
                state = self.status()['state']
                if state == 'play':
                    elapsed = self.status()['time'].split(':')[0]
                    currentsong = self.currentsong()
                    (artist, title, duration) = (currentsong.get('artist'), currentsong.get('title'), currentsong.get('time').split(":")[0])
                    if artist and title and prev != (artist, title) and is_worth_listening(int(elapsed), int(duration)):
                        prev = (artist, title)
                        try:
                            for fname in dynampd.get_a_selection(artist, title):
                                self.add(fname)
                        except ValueError, e:
                            prev = (None, None)
                            print 'Error: unable to parse Last.FM JSON ("%s"). retry in 5 seconds' % e
                time.sleep(5)
        except KeyboardInterrupt:
            if self.verbose:
                print 'Dynampd %s is now quitting...' % (__version__ )

if __name__ == '__main__':
    while True:
        try:
            Core().run()
        except IOError, e:
            print 'I/O Error while requesting Last.FM. Retrying in 20 seconds'
            time.sleep(20)
        else:
            break
