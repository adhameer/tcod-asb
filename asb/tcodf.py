"""Bits for interacting with the forums."""

import urllib.parse
import urllib.request

import bs4

def parse_tcodf_url(link):
    """Parse a TCoDf URL, and make sure it's actually a TCoDf URL."""

    parsed_link = urllib.parse.urlparse(link)

    if not parsed_link.scheme:
        # Be lenient about missing schemes
        link = 'http://{}'.format(link)
        parsed_link = urllib.parse.urlparse(link)

    if parsed_link.netloc not in ['forums.dragonflycave.com',
      'tcodforums.eeveeshq.com']:
        raise ValueError('Not a TCoDf link')

    return parsed_link

def post_id(link):
    """Parse a post link and return the post ID."""

    link = parse_tcodf_url(link)
    query = urllib.parse.parse_qs(link.query)

    if link.path not in ['/showthread.php', '/showpost.php']:
        raise ValueError('Not a post link')

    if 'p' not in query:
        raise ValueError('Missing post ID')
    elif len(query['p']) > 1:
        raise ValueError('Multiple post IDs????')

    [post_id] = query['p']

    if not post_id.isdigit():
        raise ValueError('Invalid post ID')

    return int(post_id)

def post_link(post_id):
    """Return a post link."""

    return 'http://forums.dragonflycave.com/showpost.php?p={}'.format(post_id)

def thread_id(link):
    """Parse a post or thread link and return the thread ID."""

    # People might reasonably give post links, or thread links with a post ID
    # (/showthread.php?p=12345), so we should accept those too
    try:
        post = post_id(link)
    except ValueError:
        # Not a post link — hopefully it's a thread link!
        link = parse_tcodf_url(link)
        query = urllib.parse.parse_qs(link.query)

        if link.path != '/showthread.php':
            raise ValueError('Not a thread link')

        if 't' not in query:
            raise ValueError('Missing thread ID')
        elif len(query['t']) > 1:
            raise ValueError('Multiple thread IDs????')

        [thread_id] = query['t']

        if not thread_id.isdigit():
            raise ValueError('Invalid thread ID')

        return int(thread_id)
    else:
        # Post link.  Load the thread using the post ID, and then get the
        # thread ID from the Show Printable Version link.  (Only place.)
        link = ('http://forums.dragonflycave.com/showthread.php?p={}'
            .format(post))

        page = bs4.BeautifulSoup(urllib.request.urlopen(link))

        print_link = page.find('a', text='Show Printable Version')
        print_link = urllib.parse.urlparse(print_link['href'])
        [id] = urllib.parse.parse_qs(print_link.query)['t']

        return int(id)

def thread_link(thread_id):
    """Return a thread link."""

    return ('http://forums.dragonflycave.com/showthread.php?t={}'
        .format(thread_id))

def user_id(link):
    """Given a link to a user's forum profile, parse and return the user ID."""

    link = parse_tcodf_url(link)
    query = urllib.parse.parse_qs(link.query)

    if link.path != '/member.php':
        raise ValueError('Not a forum profile link')
    elif 'u' not in query:
        raise ValueError('Missing user ID')
    elif len(query['u']) > 1:
        raise ValueError('Multiple user IDs????')
    elif not query['u'][0].isdigit():
        raise ValueError('Invalid user ID')

    return int(*query['u'])

def user_forum_link(tcodf_id):
    """Return a link to a user's forum profile."""

    return 'http://forums.dragonflycave.com/member.php?u={}'.format(tcodf_id)

def user_info(tcodf_id):
    """Given a TCoDf user ID, screenscrape their forum profile and return a
    dict of relevant info.
    """

    link = user_forum_link(tcodf_id)
    page = bs4.BeautifulSoup(urllib.request.urlopen(link))
    info = {}

    # Get their username, and make sure there even is one (vB returns 200 OK
    # even if the user doesn't exist)
    title, separator, username = page.title.text.partition(': ')

    if (title != 'The Cave of Dragonflies forums - View Profile' or
      separator != ': '):
        raise ValueError('Either the forums are down (in which case try again '
            "later), or that's not an actual user.")

    info['username'] = username

    # Get their ASB profile link, if any
    profile_dt = page.find('dt', text='ASB profile link')

    if profile_dt is None:
        info['profile_link'] = None
    else:
        info['profile_link'] = urllib.parse.urlparse(
            profile_dt.find_next('dd').string)

    return info
