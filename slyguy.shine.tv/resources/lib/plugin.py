import re

from kodi_six import xbmcplugin
from slyguy import plugin, gui, settings, userdata, signals
from slyguy.exceptions import PluginError

from .api import API
from .language import _
from .constants import *

api = API()

@signals.on(signals.BEFORE_DISPATCH)
def before_dispatch():
    api.new_session()
    plugin.logged_in = api.logged_in

@plugin.route('')
def home(**kwargs):
    folder = plugin.Folder(cacheToDisc=False)

    if not api.logged_in:
        folder.add_item(label=_(_.LOGIN, _bold=True), path=plugin.url_for(login), bookmark=False)
    else:
        folder.add_item(label=_(_.LIVE, _bold=True), path=plugin.url_for(play, slug='live', _is_live=True), playable=True)
        folder.add_item(label=_(_.BROWSE, _bold=True), path=plugin.url_for(browse))
        folder.add_item(label=_(_.SEARCH, _bold=True), path=plugin.url_for(search))
        if settings.getBool('bookmarks', True):
            folder.add_item(label=_(_.BOOKMARKS, _bold=True), path=plugin.url_for(plugin.ROUTE_BOOKMARKS), bookmark=False)

        folder.add_item(label=_.LOGOUT, path=plugin.url_for(logout), _kiosk=False, bookmark=False)

    folder.add_item(label=_.SETTINGS, path=plugin.url_for(plugin.ROUTE_SETTINGS), _kiosk=False, bookmark=False)

    return folder

@plugin.route()
def browse(page=1, **kwargs):
    page = int(page)
    folder = plugin.Folder(_.BROWSE)

    data = api.browse(page=page)
    for row in data['_embedded']['items']:
        if row['is_featured']:
            label = _.FEATURED
        else:
            label = row['name'].encode('ascii', errors='ignore').decode().strip()

        collection_id = re.search('collections/(.*?)/', row['_links']['items']['href']).group(1)

        folder.add_item(
            label = label,
            path = plugin.url_for(collection, id=collection_id, label=label),
        )

    if data['_links']['next']['href'] is not None:
        folder.add_item(
            label = _(_.NEXT_PAGE, page=page+1),
            path  = plugin.url_for(browse, page=page+1),
            specialsort = 'bottom',
        )

    return folder

@plugin.route()
def collection(id, label, page=1, default_thumb=None, **kwargs):
    page = int(page)
    folder = plugin.Folder(label)

    data = api.collection(id, page=page)
    items = _process_items(data['_embedded']['items'], default_thumb)
    folder.add_items(items)

    ## There episode numbers pretty inconsistent so just order as is
    # is_season = True
    # for item in folder.items:
    #     if not item.info.get('episode'):
    #         is_season = False

    # if is_season:
    #     folder.sort_methods = [xbmcplugin.SORT_METHOD_EPISODE, xbmcplugin.SORT_METHOD_UNSORTED, xbmcplugin.SORT_METHOD_LABEL, xbmcplugin.SORT_METHOD_DATEADDED]

    if data['_links']['next']['href'] is not None:
        folder.add_item(
            label = _(_.NEXT_PAGE, page=page+1),
            path  = plugin.url_for(collection, id=id, label=label, page=page+1, default_thumb=default_thumb),
            specialsort = 'bottom',
        )

    return folder

def _process_items(rows, default_thumb=None):
    items = []

    for row in rows:
        if row['type'] == 'video':
            thumb = row['thumbnail']['medium'] if 'default-medium' not in row['thumbnail']['medium'] else default_thumb

            if row.get('live_video'):
                label = _(_.LIVE_NOW, label=row['title'])
                path = plugin.url_for(play, slug=row['url'], _is_live=True)
            else:
                label = row['title']
                path = plugin.url_for(play, slug=row['url'])

            info = {
                'duration': row['duration']['seconds'],
                'plot': row['description'],
                'mediatype': 'movie',
            }

            if row.get('media_type') == 'episode':
                info.update({
                    'mediatype': 'episode',
                    'season': row['metadata'].get('season_number'),
                    'episode': row['metadata'].get('episode_number'),
                    'tvshowtitle': row['metadata'].get('series_name'),
                })

            items.append(plugin.Item(
                label = label,
                art = {'thumb': thumb},
                info = info,
                path = path,
                playable = True,
            ))

        elif row['type'] == 'series':
            collection_id = re.search('collections/(.*?)/', row['_links']['items']['href']).group(1)
            thumb = row['thumbnail']['medium'] if 'default-medium' not in row['thumbnail']['medium'] else default_thumb

            items.append(plugin.Item(
                label = row['name'],
                art = {'thumb': thumb},
                info = {
                    'mediatype': 'tvshow',
                    'plot': row['description'],
                },
                path = plugin.url_for(collection, id=collection_id, label=row['name'], default_thumb=thumb),
            ))

        elif row['type'] == 'season':
            collection_id = re.search('collections/(.*?)/', row['_links']['items']['href']).group(1)
            thumb = row['thumbnail']['medium'] if 'default-medium' not in row['thumbnail']['medium'] else default_thumb

            items.append(plugin.Item(
                label = _(_.SEASON, number=row['season_number']),
                art = {'thumb': thumb},
                info = {
                    'mediatype': 'season',
                    'plot': row['description'],
                },
                path = plugin.url_for(collection, id=collection_id, label=row['name'], default_thumb=thumb),
            ))

    return items

@plugin.route()
@plugin.search()
def search(query, page, **kwargs):
    data = api.search(query, page=page)
    return _process_items(data['_embedded']['collections']), data['_links']['next']['href'] is not None

@plugin.route()
def login(**kwargs):
    username = gui.input(_.ASK_EMAIL, default=userdata.get('username', '')).strip()
    if not username:
        return

    userdata.set('username', username)

    password = gui.input(_.ASK_PASSWORD, hide_input=True).strip()
    if not password:
        return

    api.login(username, password)
    gui.refresh()

@plugin.route()
@plugin.login_required()
def play(slug, **kwargs):
    url, ia = api.play(slug)

    return plugin.Item(
        path = url,
        inputstream = ia,
        headers = HEADERS,
    )

@plugin.route()
def logout(**kwargs):
    if not gui.yes_no(_.LOGOUT_YES_NO):
        return

    api.logout()
    gui.refresh()
