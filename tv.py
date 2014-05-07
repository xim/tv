#!/usr/bin/env python
# encoding: utf-8

"""
TV over python? - Oooh, the horror =)
"""

from __future__ import with_statement

import HTMLParser
import os
import subprocess
import sys
import threading
import time
import urllib2
import uuid

if 'APACHE_PID_FILE' in os.environ:
    # Hacks run if running in apache
    sys.path.insert(0, '/home/xim/dev/tv/')
    os.chdir('/home/xim/dev/tv/')

from pyroutes import route, application, utils, settings
from pyroutes.http.response import Response, Redirect
from pyroutes.template import TemplateRenderer

html_parser = HTMLParser.HTMLParser()
def unescape(string):
    return html_parser.unescape(string).decode('utf-8')

def decode_request_ch(request):
    return urllib2.unquote(request.GET.get('ch', '')).decode('utf-8')


renderer = TemplateRenderer("templates/base.xml")
# Yes, we use a global variable to hold the names of the currently
# playing channels.
playing = {}

def random_secret():
    """
    Yes, we generate one time passwords that are reset when the process
    dies or someone stops watching a channel
    """
    return uuid.uuid4().hex
secret = random_secret()

# Re-use this for waring on active channel
ACTIVE_WARNING = u"""
Aktive kanaler: %s.
"""

class ChannelListingError(Exception):
    """Exception

    for catching errors when playlist.html is not the expected m3u form
    """
    pass

class Channels(dict):
    """Channels

    Gets http://forskningsnett.uninett.no/tv/playlist.html
    Makes it into a dict
    """
    def __init__(self):
        super(Channels, self).__init__()
        self._populate()

    def _populate(self):
        """ Actually generates the channel list """
        response = urllib2.urlopen(
                'http://forskningsnett.uninett.no/tv/playlist.html')
        raw_pl = [x.strip() for x in response.readlines()[1:]]
        while raw_pl:
            try:
                url = raw_pl.pop()
                name = raw_pl.pop()
                if url.startswith('#') or not name.startswith('#EXTINF:0'):
                    raise ChannelListingError('Listing order is fucked?')
                self[unescape(name[10:])] = url
            except IndexError:
                raise ChannelListingError('Channel with missing description?')

# Yes, channels are re-fetched every time the file is loaded.
channels = Channels()

@route('/')
def main(request):
    """Keep all pages different sub-URLs, not on /

    in case we want to make a different front page or whatever
    """
    return Redirect('/listing/')

@route('/listing')
def listing(request):
    """ Create a simple listing from the channels object """
    template_data = { 'channels': [] }

    if 'tv' in request.GET:
        template_data['styles'] = [{'link/href': '/media/tv.css',
                                    'link/rel': 'stylesheet',
                                    'link/type': 'text/css'}]

    for channel in sorted(channels):
        channel_uripart = urllib2.quote(channel.encode('utf-8'))
        template_data['channels'].append({
            'dl': {
                'dt': channel,
                '#dd1': {
                    'a': 'Start en proxy',
                    'a/href': 'http://' + request.ENV['HTTP_HOST']
                    + settings.SITE_ROOT + '/url/' + secret + '/?ch='
                    + channel_uripart},
                '#dd2': {
                    'a': 'Direktelenke',
                    'a/href': 'http://' + request.ENV['HTTP_HOST']
                    + settings.SITE_ROOT + '/redirect/' + secret + '/?ch='
                    + channel_uripart}
            }
        })
    if playing:
        template_data['#playing'] = ACTIVE_WARNING % ', '.join(playing.keys())
        template_data['#playing/style'] = 'color: red'

    return Response(renderer.render("templates/listing.xml", template_data))

class VLCMonitor(threading.Thread):
    """Here be dragons :)

    Holds threads that watch the VLC processes, and kill them when noone
    is watching -- using /proc/<pid>/net/tcp
    """

    def __init__(self, vlc, channel):
        super(VLCMonitor, self).__init__()
        self.vlc = vlc
        self.channel = channel
        self.port = playing[channel]

    def run(self):
        """ The code that is run while doing the actual monitoring """
        time.sleep(45)
        # Wait for process exit
        while self.monitor():
            time.sleep(15)

        global playing
        del playing[self.channel]

        sys.stderr.write('killing vlc...')
        # ^C the process
        os.kill(self.vlc.pid, 2)
        # Wait a moment
        time.sleep(3)
        if self.vlc.poll() is None:
            sys.stderr.write('vlc not responding (%r). KILL!' % self.vlc.pid)
            # KILL DASH NINE if it hasn't exited
            os.kill(self.vlc.pid, 9)

    def monitor(self):
        """ Try to find incoming TCP connections for this VLC """
        with open('/proc/%d/net/tcp' % self.vlc.pid, 'r') as netstat:
            try:
                netstat.readline()
                for line in netstat:
                    line = line.strip().split()
                    inode = line[9]
                    state = line[3]
                    port = int(line[1].split(':')[1], 16)
                    if state == '01' and port == self.port:
                        for fd in os.listdir('/proc/%d/fd' % self.vlc.pid):
                            if os.stat('/proc/%d/fd/%s' % (self.vlc.pid, fd) \
                                    ).st_ino == int(inode):
                                # Return True on first active, relevant TCP
                                return True
            except Exception, e:
                sys.stderr.write(e.__class__.__name__ + ': ' + e)
                return False
        return False

def magic(request, key=''):
    """Common VLC starting magic

    Returns a HTTP URL with port and key for a running VLC process
    """
    port = 3337
    if key != secret:
        # 4 the lulz
        # http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.4.3
        return Response("""Ugyldig nøkkel.
            G\xc3\xa5 tilbake til <a href="../listing">kanaloversikten</a>.""",
                status_code=402)
    channel = decode_request_ch(request)
    if not channel in channels:
        return Response('Ugyldig eller manglende kanal',
                status_code=500)

    global playing
    if not channel in playing:
        while port in playing.values():
            port += 1
        # vlc for forwarding streams is easy! ♥
        vlc = subprocess.Popen(
            ['/usr/bin/vlc',
            '-Idummy',
            channels[channel],
            '--sout',
            '#std{access=http,mux=ts,dst=0.0.0.0:%d/%s}' % (port, secret)]
            )
        playing[channel] = port
        VLCMonitor(vlc, channel).start()
    else:
        port = playing.get(channel, port)

    return 'http://%s:%d/%s' % \
            (request.ENV['HTTP_HOST'].split(':')[0], port, secret)

@route('/url')
def url_page(request, key=''):
    """ List all available formats for a channel """
    response = magic(request, key)
    if isinstance(response, Response):
        return response

    template_data = {'#url/href': response}
    for p in ['html5_player', 'object_player', 'm3u', 'pls', 'xspf', 'asx']:
        template_data['#' + p + '/href'] = '../../' + p + '/' \
                + urllib2.quote(key) + '/?ch=' + decode_request_ch(request)
    return Response(renderer.render("templates/url.xml", template_data))

@route('/redirect')
def redirect_page(request, key=''):
    """ Sleep a second and redirect to the stream. My fav. """
    if request.ENV.get('REQUEST_METHOD', '') == 'HEAD':
        return Redirect('/head/')
    response = magic(request, key)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    return Redirect(response, [('Cache-Control','no-cache')])

@route('/head')
def head_redirect_target(request):
    return Response('', [('Content-type', 'application/octet-stream')])

@route('/object_player')
def object_player(request, key=''):
    """ HTML <object> player """
    return player_page(request, key, 'templates/object_player.xml',
            '#src/value')

@route('/html5_player')
def html5_player(request, key=''):
    """ HTML5 <video> player """
    return player_page(request, key, 'templates/html5_player.xml', '#src/src')

def player_page(request, key, template, attr):
    """ Generic stuff for making an embedded player """
    response = magic(request, key)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    channel = decode_request_ch(request)
    template_data = {'#title': channel}
    template_data[attr] = response
    return Response(renderer.render(template, template_data))

@route('/pls')
def pls_dl(request, key=''):
    """ Makes a .pls file """
    response = magic(request, key)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    channel = decode_request_ch(request)
    playlist = '''[playlist]
File1=%s
Title1=%s
Length1=-1
NumberOfEntries=1''' % (response, channel)
    return Response(playlist,
            headers=[('Content-type','audio/x-scpls'),
                 ('Content-disposition', 'attachment;filename=tv.pls')])

@route('/m3u')
def m3u_dl(request, key=''):
    """ Makes an m3u file """
    response = magic(request, key)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    return Response(response,
            headers=[('Content-type','audio/x-mpegurl'),
                 ('Content-disposition', 'attachment;filename=tv.m3u')])

@route('/asx')
def asx_dl(request, key=''):
    """ Microsoft asx, XML based format """
    response = magic(request, key)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    channel = decode_request_ch(request)
    template_data = {
            '#url/href': response,
            '#title': channel,
            }
    return Response(
            TemplateRenderer().render("templates/asx.xml", template_data),
            headers=[('Content-type','video/x-ms-asf'),
                 ('Content-disposition', 'attachment;filename=tv.asf')])

@route('/xspf')
def xspf_dl(request, key=''):
    """ XSPF, an XML based playlist format """
    response = magic(request, key)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    channel = decode_request_ch(request)
    template_data = {'#url': response, '#title': channel}
    return Response(
            TemplateRenderer().render("templates/xspf.xml", template_data),
            headers=[('Content-type','application/xspf+xml'),
                 ('Content-disposition', 'attachment;filename=tv.xspf')])

if __name__ == '__main__':
    # For when we are running tv.py from the shell

    port = 8001
    address = '0.0.0.0'
    if sys.argv[1:]:
        try:
            address, port = sys.argv[1].rsplit(':', 1)
            port = int(port)
        except ValueError:
            sys.stderr.write(
'''If you want to supply a listen address, it must be on the format IP:port
Examples:
  ./tv.py :80            # Listen on all IPv4 addresses, on the HTTP port
  ./tv.py 127.0.0.1:8000 # Run on localhost, good for development
''')
    route('/media')(utils.fileserver)
    utils.devserver(application, address=address, port=port)
