from .. import *
from ._utils import *

import urllib
from tqdm import tqdm
from bs4 import BeautifulSoup

def _get_image_url(raw_link):
    parse_res = list(urllib.parse.urlparse(raw_link))
    if not parse_res[0]:
        parse_res[0] = 'https'
    if not parse_res[1]:
        parse_res[1] = 'img.linovelib.com'
    return urllib.parse.urlunparse(parse_res)


def _read_metadata_item(metadata, name):
    item = re.search(f'{name}:\'([^\']*)\'', metadata)
    if item:
        return item.group(1)
    return None


def _read_metadata(metadata):
    url_previous = _read_metadata_item(metadata, 'url_previous')
    url_next = _read_metadata_item(metadata, 'url_next')
    chapterid = _read_metadata_item(metadata, 'chapterid')
    page = _read_metadata_item(metadata, 'page')
    return {
        'url_previous': url_previous,
        'url_next': url_next,
        'chapterid': chapterid,
        'page': page,
    }


def _get_one_page(link, encoding='utf8'):
    page_str = requests_get(f'https://w.linovelib.com{link}')
    if page_str is None:
        raise Exception(f'Getting page failed: {link}')
    page = BeautifulSoup(page_str.decode(encoding), 'html.parser')

    metadata_tag = page.find('body').find('script', type='text/javascript')
    metadata = metadata_tag.text
    metadata = _read_metadata(metadata)

    content_tag = page.find('div', id='acontent')

    cgo = content_tag.find('div', class_='cgo')
    if cgo:
        cgo.decompose()
    google_ads = content_tag.find_all('div', class_='google-auto-placed')
    for _ad in google_ads:
        _ad.decompose()

    content_tag.attrs.clear()
    return content_tag, metadata


def _get_page(link, encoding='utf8'):
    contents = []
    image_tags = []
    content_tag, metadata = _get_one_page(link, encoding=encoding)
    _image_tags = content_tag.find_all('img')
    image_tags.extend(_image_tags)
    contents.append(content_tag)
    next_url = None
    while not metadata['url_next'].endswith('catalog'):
        current_id = metadata['chapterid']
        next_link = metadata['url_next']
        next_content_tag, next_metadata = _get_one_page(next_link, encoding=encoding)
        if next_metadata['chapterid'] != current_id:
            next_url = next_link
            break
        _image_tags = next_content_tag.find_all('img')
        image_tags.extend(_image_tags)
        contents.append(next_content_tag)
        metadata = next_metadata
    return contents, image_tags, next_url


def _get_prev_page_link(link, hop=1, encoding='utf8'):
    content_tag, metadata = _get_one_page(link, encoding=encoding)
    searched = 0
    while True:
        prev_id = metadata['chapterid']
        prev_link = link
        link = metadata['url_previous']
        if link.endswith('catalog'):
            break
        content_tag, metadata = _get_one_page(link, encoding=encoding)
        if metadata['chapterid'] != prev_id:
            searched += 1
            if searched > hop:
                break
    return prev_link


def grab(postfix, reverse=False, skip=True, path='out_linovelib', **kwargs):
    web_src = f'https://w.linovelib.com/novel/{postfix}/catalog'
    encoding = 'utf8'

    mainpage_str = requests_get(web_src)
    if mainpage_str is None:
        raise Exception(f'Getting main page failed: {web_src}')
    mainpage_content = mainpage_str
    mainpage = BeautifulSoup(mainpage_content.decode(encoding), 'html.parser')

    title = mainpage.find('h1', class_='header-back-title').text
    volumes = mainpage.find(id='volumes')

    chapter_tags = volumes.find_all('li', class_='chapter-li')
    chapters = []
    _chapter_name = None
    _chapter_buf = []
    for _ctag in chapter_tags:
        if 'chapter-bar' in _ctag.attrs['class']:
            # bar
            if _chapter_buf:
                none_count = 0
                for i in range(len(_chapter_buf) - 1, -1, -1):
                    name, href = _chapter_buf[i]
                    _chapter_buf[i] = (name, href, none_count)
                    if href is None:
                        none_count += 1
                    else:
                        none_count = 0
                if _chapter_buf and _chapter_buf[0][1] is None:
                    name, href, none_count = _chapter_buf[0]
                    next_not_none_index = none_count + 1
                    if next_not_none_index >= len(_chapter_buf):
                        raise Exception(f'Invalid links for chapter {_chapter_name}')
                    href = _get_prev_page_link(_chapter_buf[next_not_none_index][1], hop=next_not_none_index,
                                               encoding=encoding)
                    _chapter_buf[0] = (name, href, none_count)
                chapters.append((_chapter_name, _chapter_buf))
                _chapter_buf = []
            _chapter_name = _ctag.text
        else:
            a = _ctag.find('a', class_='chapter-li-a')
            name = _ctag.find('span', class_='chapter-index')
            href = a.attrs['href']
            if href.startswith('javascript'):
                href = None
            _chapter_buf.append((name.text, href))
    if _chapter_buf:
        none_count = 0
        for i in range(len(_chapter_buf) - 1, -1, -1):
            name, href = _chapter_buf[i]
            _chapter_buf[i] = (name, href, none_count)
            if href is None:
                none_count += 1
            else:
                none_count = 0
        if _chapter_buf and _chapter_buf[0][1] is None:
            name, href, none_count = _chapter_buf[0]
            next_not_none_index = none_count + 1
            if next_not_none_index >= len(_chapter_buf):
                raise Exception(f'Invalid links for chapter {_chapter_name}')
            href = _get_prev_page_link(_chapter_buf[next_not_none_index][1], hop=next_not_none_index, encoding=encoding)
            _chapter_buf[0] = (name, href, none_count)
        chapters.append((_chapter_name, _chapter_buf))

    _chapters = []
    first_exists = False
    for chapter_name, chapter_pages in reversed(chapters):
        epub_file = file_escape(f'{title} {chapter_name}')
        file_exists = os.path.isfile(f'{path}/{epub_file}.epub')
        if skip and file_exists:
            # To update the last existing book discovered
            _skip = first_exists
            first_exists = True
        else:
            _skip = False
        _chapters.append((_skip, file_exists, epub_file, chapter_name, chapter_pages))

    if not reverse:
        _chapters = reversed(_chapters)

    for _skip, overwrite, epub_file, chapter_name, chapter_pages in _chapters:
        if _skip:
            continue
        contents = []
        images = []
        img_count = 0
        cover_dst = None
        next_url = None
        if overwrite:
            desc = f'Update: {epub_file}'
        else:
            desc = f'New:    {epub_file}'
        for index, (page_name, first_page_link, none_count) in tqdm(enumerate(chapter_pages), desc=desc,
                                                                    total=len(chapter_pages)):
            if first_page_link is None:
                first_page_link = next_url
            if first_page_link is None:
                raise Exception(f'Invalid link for page {epub_file} : {page_name}')
            page_content, image_tags, next_url = _get_page(first_page_link, encoding=encoding)
            page_id = f'page{index}'
            page_title = page_name
            for img in image_tags:
                img_link = img.attrs['src']
                img_file = f'temp/{file_escape(img_link)}'
                img_id = f'image{img_count}'
                img_ext = ext(img_link)
                img_dst = f'{img_id}.{img_ext}'
                if cover_dst is None:
                    cover_dst = f'cover.{img_ext}'
                if not os.path.isfile(img_file):
                    img_content = requests_get(_get_image_url(img_link))
                    if img_content is None:
                        raise Exception(f'Getting image failed: {img_link}')
                    with open(img_file, 'wb') as f:
                        f.write(img_content)
                img.attrs = {'src': 'images/' + img_dst}
                img_count += 1
                images.append((img_id, img_file, img_dst))
            contents.append((page_id, page_title, ''.join(map(str, page_content))))

        _epub = Epub(title, author=None)
        for id_, src, dst in images:
            _epub.add_image(id_, src, dst)
        for id_, page_title, page_content in contents:
            _epub.add_page(id_, page_title, page_content)
        if cover_dst is not None:
            _epub.add_cover(images[0][1], cover_dst)
            _epub.add_cover_page('cover', '', Page.cover(cover_dst, 'cover.html', _epub.metadata, ''))
        _epub.generate(epub_file, remove=True, path=path)

def search(title, page=1, **kwargs):
    encoding = 'utf8'
    quoted_title = urllib.parse.quote(title, encoding=encoding)
    if not isinstance(page, int) or page < 1:
        page = 1
    #link = f'https://w.linovelib.com/S8/{quoted_title}_{page}.html'
    link = f'https://w.linovelib.com/S8/?searchkey={quoted_title}&searchtype=all&page={page}'

    page_response = requests.get(link, allow_redirects=False)
    if page_response.is_redirect:
        next_url = page_response.next.url
        m = re.search(r'novel/([0-9]+).html', next_url)
        if m:
            book_id = int(m.group(1))
            total_items = 1
            current_page = 1
            total_pages = 1

            page_str = requests_get(next_url)
            if page_str is None:
                raise Exception(f'Getting book page failed: {link}')

            page_content = page_str
            page = BeautifulSoup(page_content.decode(encoding), 'html.parser')

            book_info_tag = page.find('div', class_='book-detail-info')

            title_tag = book_info_tag.find('h2', class_='book-title')
            title = title_tag.text

            author_tag = book_info_tag.find('div', class_='book-rand-a').find('span')
            author = author_tag.text

            cover_tag = page.find('div', id='bookDetailWrapper').find('img', class_='book-cover-blur')
            cover_link = cover_tag.attrs['src']

            desc_tag = page.find('section', id='bookSummary')
            if desc_tag:
                desc = desc_tag.text
            else:
                desc = ''

            book_info = {
                'id': book_id,
                'title': title,
                'author': author,
                'description': desc,
                'cover': cover_link,
            }
        else:
            raise Exception(f'Failed to get book ID: {next_url}')
        return {
            'total': total_items,
            'current_page': current_page,
            'total_pages': total_pages,
            'items': [book_info],
        }

    page_str = page_response.content
    if page_str is None:
        raise Exception(f'Getting search page failed: {link}')
    page_content = page_str
    page = BeautifulSoup(page_content.decode(encoding), 'html.parser')

    total_items_tag = page.find('h3', class_='module-title')
    total_items_text = total_items_tag.text
    m = re.search(r'共有 *([0-9]+) *条记录', total_items_text)
    if m:
        total_items = int(m.group(1))
    else:
        total_items = None

    current_page = None
    total_pages = None
    total_pages_tag = page.find('div', id='pagelink')
    if total_pages_tag:
        total_pages_text = total_pages_tag.find('span').text
        m = re.search(r'第 *([0-9]+) */ *([0-9]+) *页', total_pages_text)
        if m:
            current_page, total_pages = int(m.group(1)), int(m.group(2))

    all_items_tag = page.find('ol', class_='book-ol')
    item_tags = all_items_tag.find_all('li', class_='book-li')

    items = []
    for item_tag in item_tags:
        book_id_tag = item_tag.find('a', class_='book-layout')
        book_id_text = book_id_tag.attrs['href']
        m = re.search(r'novel/([0-9]+).html', book_id_text)
        if m:
            book_id = int(m.group(1))
        else:
            book_id = None
        title_tag = item_tag.find('h4', class_='book-title')
        title = title_tag.text
        author_tag = item_tag.find('span', class_='book-author')
        author_tag.find('title').clear()
        author = author_tag.text
        cover_tag = item_tag.find('img', class_='book-cover')
        cover_link = cover_tag.attrs['src']
        desc_tag = item_tag.find('p', class_='book-desc')
        desc = desc_tag.text

        item = {
            'id': book_id,
            'title': title,
            'author': author,
            'description': desc,
            'cover': cover_link,
        }
        items.append(item)

    return {
        'total': total_items,
        'current_page': current_page,
        'total_pages': total_pages,
        'items': items,
    }

__all__ = ['grab', 'search']
