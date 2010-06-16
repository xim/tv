#!/usr/bin/env python

from __future__ import with_statement

import os
import subprocess
import sys
import threading
import time
import urllib2

if 'APACHE_PID_FILE' in os.environ:
    # Hacks run if running in apache
    sys.path.insert(0, '/home/xim/dev/tv/')
    os.chdir('/home/xim/dev/tv/')

from pyroutes import route, application, utils
from pyroutes.http.response import Response, Redirect
from pyroutes.template import TemplateRenderer

"""
TV over python elns
"""


renderer = TemplateRenderer("templates/base.xml")
global playing
playing = None

def random_secret(bits=16):
    with open('/dev/urandom') as f:
        return urllib2.quote(f.read(bits).encode('base64').strip().rstrip('='))
global secret
secret = random_secret()

class ChannelListingError(Exception):
    pass

class Channels(dict):
    def __init__(self):
        super(Channels, self).__init__()
    def get_list(self):
        if not self:
            self._populate()
        return self
    def _populate(self):
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

channels = Channels()

@route('/')
def main(request):
    return Redirect('/listing/')

@route('/listing')
def listing(request):
    template_data = {'channels': []}
    ch_copy = dict(channels.get_list())
    for c in sorted(ch_copy.keys(), lambda x,y: cmp(ch_copy[x],ch_copy[y])):
        template_data['channels'].append({'dl':
            {'dt': ch_copy[c],
             '#dd1': {'a': 'Start en proxy', 'a/href': 'http://' + request.ENV['HTTP_HOST'] + '/url/?otp=' + secret + '&ch=' + urllib2.quote(c)},
             '#dd2': {'a': 'Direktelenke', 'a/href': 'http://' + request.ENV['HTTP_HOST'] + '/redirect/?otp=' + secret + '&ch=' + urllib2.quote(c)}}})
    if playing is not None:
        template_data['#playing'] = 'Someone already watching! Channel is locked to %s' % playing
        template_data['#playing/style'] = 'color: red'
    return Response(renderer.render("templates/listing.xml", template_data))

class VLCMonitor(threading.Thread):

    def __init__(self, vlc, port):
        super(VLCMonitor, self).__init__()
        self.vlc = vlc
        self.port = port

    def run(self):
        time.sleep(30)
        while self.monitor():
            time.sleep(5)

        global secret, playing
        secret = random_secret()
        playing = None

        sys.stderr.write('killing vlc...')
        os.kill(self.vlc.pid, 2)
        time.sleep(3)
        poll = self.vlc.poll()
        if self.vlc.poll() is None:
            sys.stderr.write('vlc not responding (%r). KILL!' % poll)
            os.kill(self.vlc.pid, 9)

    def monitor(self):
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
                            if os.stat('/proc/%d/fd/%s' % (self.vlc.pid,fd)).st_ino == int(inode):
                                #print pid, inode, port, state, line
                                return True
            except Exception, e:
                sys.stderr.write(e.__class__.__name__ + ': ' + e)
                return False
        return False

def magic(request):
    port = 3337
    global secret
    otp = request.GET.get('otp', '')
    if otp != urllib2.unquote(secret):
        return Response('Invalid one time password token. Return to <a href="/listing">listing</a> and retry', status_code='402 Payment Required')
    if not 'ch' in request.GET or len(request.GET['ch']) < 6:
        return Response('No channel defined or no protocol', status_code='500 Server Error')
    stream = request.GET['ch']
    protocol = stream[0:6]
    if protocol != 'rtp://' and protocol != 'udp://':
        stream = '/home/xim/nobackup/alex_gaudino_-_destination_calabria.avi'

    global playing
    if playing is None:
        vlc = subprocess.Popen(
            ['/usr/bin/vlc',
            '-Idummy',
            stream,
            '--sout',
            '#std{access=http,mux=ts,dst=0.0.0.0:%d/%s}' % (port,secret)]
            )
        playing = channels.get(stream, stream)
        VLCMonitor(vlc, port).start()

    return 'http://%s:%d/%s' % (request.ENV['HTTP_HOST'].split(':')[0], port, secret)

@route('/url')
def url_page(request):
    template_data = {}

    response = magic(request)
    if isinstance(response, Response):
        return response
    template_data['#url/href'] = response
    global playing
    stream = request.GET['ch']
    if playing != channels.get(stream, stream):
        template_data['#playing'] = 'Someone watching a different channel! Channel is locked to %s' % playing
        template_data['#playing/style'] = 'color: red'
    for p in ['html5_player', 'object_player', 'm3u', 'pls', 'xspf', 'asx']:
        template_data['#' + p + '/href'] = '/' + p + '/?otp=' + urllib2.quote(request.GET['otp']) + '&ch=' + request.GET['ch']
    return Response(renderer.render("templates/url.xml", template_data))

@route('/redirect')
def redirect_page(request):
    response = magic(request)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    return Redirect(response)

@route('/object_player')
def object_player(request):
    return player_page(request)

@route('/html5_player')
def html5_player(request):
    return player_page(request, 'templates/html5_player.xml', '#src/src')

def player_page(request, template='templates/object_player.xml', attr='#src/value'):
    response = magic(request)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    stream = request.GET['ch']
    template_data = {'#title': channels.get(stream, stream)}
    template_data[attr] = response
    global playing
    if playing != template_data['#title'] and playing != response:
        template_data['#playing'] = 'Someone watching a different channel! Channel is locked to %s' % playing
        template_data['#playing/style'] = 'color: red'
    return Response(renderer.render(template, template_data))

@route('/pls')
def pls_dl(request):
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
    response = magic(request)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    return Response(response, default_content_header=False,
            headers=[('Content-type','audio/x-mpegurl'),
                 ('Content-disposition', 'attachment;filename=tv.m3u')])

@route('/asx')
def asx_dl(request):
    response = magic(request)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    stream = request.GET['ch']
    template_data = {'#url/href': response, '#title': channels.get(stream, stream)}
    return Response(TemplateRenderer().render("templates/asx.xml", template_data),
            default_content_header=False,
            headers=[('Content-type','video/x-ms-asf'),
                 ('Content-disposition', 'attachment;filename=tv.asf')])

@route('/xspf')
def xspf_dl(request):
    response = magic(request)
    if isinstance(response, Response):
        return response
    time.sleep(1)
    stream = request.GET['ch']
    template_data = {'#url': response, '#title': channels.get(stream, stream)}
    return Response(TemplateRenderer().render("templates/xspf.xml", template_data),
            default_content_header=False,
            headers=[('Content-type','application/xspf+xml'),
                 ('Content-disposition', 'attachment;filename=tv.xspf')])

if __name__ == '__main__':
    route('/media')(utils.fileserver)
    utils.devserver(application)
