#!/usr/bin/env python
# encoding: utf-8

"""
TV over python? - Oooh, the horror =)
"""

from __future__ import with_statement

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

from pyroutes import route, application, utils
from pyroutes.http.response import Response, Redirect
from pyroutes.template import TemplateRenderer


renderer = TemplateRenderer("templates/base.xml")
# Yes, we use a global variable to hold the name of the currently
# playing channel.
playing = None

def random_secret():
    """
    Yes, we generate one time passwords that are reset when the process
    dies or someone stops watching a channel
    """
    return urllib2.quote(uuid.uuid4().hex.encode('base64').strip().rstrip('='))
secret = random_secret()

# Re-use this for waring on active channel
ACTIVE_WARNING = u"""
Noen ser på kanalen %s.
Det er kun mulig å se denne kanalen for øyeblikket.
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
    def get_list(self):
        """ Get list, creating it if it doesn't exist """
        if not self:
            self._populate()
        return self
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
                self[url] = name[10:]
            except IndexError:
                raise ChannelListingError('Channel with missing discription?')

# Yes, channels are re-fetched every time the file is loaded.
channels = Channels()

@route('/')
def main(request):
    """Keep all pages different sub-URLs, not on /

    in case we want to make a different front page
    """
    return Redirect('/listing/')

@route('/listing')
def listing(request):
    """ Create a simple listing from the channels object """
    template_data = {'channels': []}
    ch_copy = dict(channels.get_list())
    for ch in sorted(ch_copy.keys(), lambda x, y: cmp(ch_copy[x], ch_copy[y])):
        template_data['channels'].append({'dl':
            {'dt': ch_copy[ch],
                '#dd1': {'a': 'Start en proxy',
                    'a/href': 'http://' + request.ENV['HTTP_HOST'] +
                    '/url/?otp=' + secret + '&ch=' + urllib2.quote(ch)
                    },
                '#dd2': {'a': 'Direktelenke',
                    'a/href': 'http://' + request.ENV['HTTP_HOST'] +
                    '/redirect/?otp=' + secret + '&ch=' + urllib2.quote(ch)}}})
    if playing is not None:
        template_data['#playing'] = ACTIVE_WARNING % playing
        template_data['#playing/style'] = 'color: red'
    return Response(renderer.render("templates/listing.xml", template_data))

class VLCMonitor(threading.Thread):
    """Here be dragons :S

    Holds threads that watch the VLC processes, and kill them when noone
    is watching -- using /proc/<pid>/net/tcp
    """

    def __init__(self, vlc, port):
        super(VLCMonitor, self).__init__()
        self.vlc = vlc
        self.port = port

    def run(self):
        """ The code that is run while doing the actual monitoring """
        time.sleep(30)
        # Wait for process exit
        while self.monitor():
            time.sleep(5)

        # Reset OTP
        global secret, playing
        secret = random_secret()
        playing = None

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

def magic(request):
    """Common VLC starting magic

    Returns a HTTP URL with OTP for the running VLC process
    """
    port = 3337
    otp = request.GET.get('otp', '')
    if otp != urllib2.unquote(secret):
        # 4 the lulz
        # http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.4.3
        return Response("""Ugyldig engangspassord.
                G\xc3\xa5 tilbake til <a href="/listing">kanaloversikten</a>.""",
                status_code='402 Payment Required')
    if not 'ch' in request.GET or len(request.GET['ch']) < 6:
        return Response('Ugyldig eller manglende adresse til kanal',
                status_code='500 Server Error')
    stream = request.GET['ch']
    protocol = stream[0:6]
    if protocol != 'rtp://' and protocol != 'udp://':
        # TODO: Replace with an MPEG
        stream = '/home/xim/nobackup/alex_gaudino_-_destination_calabria.avi'

    global playing
    if playing is None:
        # vlc for forwarding streams is easy! ♥
        vlc = subprocess.Popen(
            ['/usr/bin/vlc',
            '-Idummy',
            stream,
            '--sout',
            '#std{access=http,mux=ts,dst=0.0.0.0:%d/%s}' % (port,secret)]
            )
        playing = channels.get(stream, stream)
        VLCMonitor(vlc, port).start()

    return 'http://%s:%d/%s' % \
            (request.ENV['HTTP_HOST'].split(':')[0], port, secret)

@route('/url')
def url_page(request):
    """ List all available formats for a channel """
    template_data = {}

    response = magic(request)
    if isinstance(response, Response):
        return response
    template_data['#url/href'] = response
    stream = request.GET['ch']
    if playing != channels.get(stream, stream):
        template_data['#playing'] = ACTIVE_WARNING % playing
        template_data['#playing/style'] = 'color: red'
    for p in ['html5_player', 'object_player', 'm3u', 'pls', 'xspf', 'asx']:
        template_data['#' + p + '/href'] = \
                '/' + p + '/?otp=' + urllib2.quote(request.GET['otp']) + \
                '&ch=' + request.GET['ch']
    return Response(renderer.render("templates/url.xml", template_data))

@route('/redirect')
def redirect_page(request):
    """ Sleep a second and redirect to the stream. My fav. """
    response = magic(request)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    return Redirect(response)

@route('/object_player')
def object_player(request):
    """ HTML <object> player """
    return player_page(request, 'templates/object_player.xml', '#src/value')

@route('/html5_player')
def html5_player(request):
    """ HTML5 <video> player """
    return player_page(request, 'templates/html5_player.xml', '#src/src')

def player_page(request, template, attr):
    """ Generic stuff for making an embedded player """
    response = magic(request)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    stream = request.GET['ch']
    template_data = {'#title': channels.get(stream, stream)}
    template_data[attr] = response
    if playing != template_data['#title'] and playing != response:
        template_data['#playing'] = ACTIVE_WARNING % playing
        template_data['#playing/style'] = 'color: red'
    return Response(renderer.render(template, template_data))

@route('/pls')
def pls_dl(request):
    """ Makes a .pls file """
    response = magic(request)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    stream = request.GET['ch']
    playlist = '''[playlist]
File1=%s
Title1=%s
Length1=-1
NumberOfEntries=1''' % (response, channels.get(stream, stream))
    return Response(playlist, default_content_header=False,
            headers=[('Content-type','audio/x-scpls'),
                 ('Content-disposition', 'attachment;filename=tv.pls')])

@route('/m3u')
def m3u_dl(request):
    """ Makes an m3u file """
    response = magic(request)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    return Response(response, default_content_header=False,
            headers=[('Content-type','audio/x-mpegurl'),
                 ('Content-disposition', 'attachment;filename=tv.m3u')])

@route('/asx')
def asx_dl(request):
    """ Microsoft asx, XML based format """
    response = magic(request)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    stream = request.GET['ch']
    template_data = {
            '#url/href': response,
            '#title': channels.get(stream, stream)
            }
    return Response(
            TemplateRenderer().render("templates/asx.xml", template_data),
            default_content_header=False,
            headers=[('Content-type','video/x-ms-asf'),
                 ('Content-disposition', 'attachment;filename=tv.asf')])

@route('/xspf')
def xspf_dl(request):
    """ XSPF, an XML based playlist format """
    response = magic(request)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    stream = request.GET['ch']
    template_data = {'#url': response, '#title': channels.get(stream, stream)}
    return Response(
            TemplateRenderer().render("templates/xspf.xml", template_data),
            default_content_header=False,
            headers=[('Content-type','application/xspf+xml'),
                 ('Content-disposition', 'attachment;filename=tv.xspf')])

if __name__ == '__main__':
    # For when we are running tv.py from the shell
    # I've seen the media server bug in chromium. Should be debugged...
    route('/media')(utils.fileserver)
    utils.devserver(application)
