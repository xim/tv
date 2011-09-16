"""
Stream from TV.py! =)
"""

import sys
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

import urllib2
import re

addon = xbmcaddon.Addon(id='plugin.video.tv')

def get_listing(username, password, url):
    url = url or 'https://tv.akuma.no/listing/'
    auth = 'Basic ' + ('%s:%s' % (username, password)).encode('base64')
    request = urllib2.Request(url, headers={'Authorization': auth})
    page = urllib2.urlopen(request)
    channels = []
    channel_name = ''
    for line in page:
        match = re.match(r'.*<dt>(.*)</dt>.*', line)
        if match:
            channel_name = match.groups()[0]
        else:
            match = re.match(r'.*href="(.*)">Direktelenke.*', line)
            if match:
                channels.append((channel_name, match.groups()[0]))
    return channels

def main():
    xbmc.log('TV.py plugin loaded')
    username = addon.getSetting('username')
    password = addon.getSetting('password')
    while not username or not password:
        addon.openSettings(sys.argv[0])
        username = addon.getSetting('username')
        password = addon.getSetting('password')

    xbmc.log('Getting listing')
    listing = get_listing(username, password, addon.getSetting('server_url'))
    xbmc.log('Iterating')
    for title, url in listing:
        listitem=xbmcgui.ListItem(title)
        listitem.setInfo(type='Video', infoLabels={'Title': title})
        xbmcplugin.addDirectoryItem(
                handle=int(sys.argv[1]),
                url=url,
                listitem=listitem,
                isFolder=False,
                totalItems=len(listing))

    xbmcplugin.endOfDirectory(handle=int(sys.argv[1]), succeeded=1)

    xbmc.log('Done!')

if __name__ == "__main__":
    main()
