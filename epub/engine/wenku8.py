from .. import *
from ._utils import *

import urllib
from tqdm import tqdm
from bs4 import BeautifulSoup

def grab(postfix, reverse=False, skip=True, path='out_wenku8', **kwargs):
    prefix = postfix // 1000
    web_src = f'https://www.wenku8.net/novel/{prefix}/{postfix}/'
    encoding = 'GB18030'

    mainpage_str = requests_get(web_src)
    if mainpage_str is None:
        raise Exception(f'Getting main page failed: {web_src}')
    mainpage_content = mainpage_str
    mainpage = BeautifulSoup(mainpage_content.decode(encoding), 'html.parser')
    title = mainpage.find('div', id='title').text
    info = mainpage.find('div', id='info').text

    books = []
    table = mainpage.find('table', class_='css')
    tds = table.find_all('td')

    cur_book = None
    cur_title = None
    for td in tds:
        if td.attrs.get('class', [None])[0] == 'vcss':
            if cur_title is not None:
                books.append((cur_title, cur_book))
            cur_book = []
            cur_title = f'{title} {td.text}'
        elif cur_book is not None:
            a = td.find('a')
            if a is not None:
                link = web_src + a.attrs['href']
                label = a.text
                cur_book.append((link, label))
    if cur_title is not None:
        books.append((cur_title, cur_book))

    _books = []
    for index, (cur_title, cur_book) in enumerate(reversed(books)):
        if skip:
            _skip = index != 0
        else:
            _skip = False
        _books.append((_skip, cur_title, cur_book))

    if not reverse:
        _books = reversed(_books)

    for _skip, title, book in _books:
        epub_file = file_escape(title)
        overwrite = os.path.isfile(f'{path}/{epub_file}.epub')
        if _skip and overwrite:
            continue
        contents = []
        images = []
        img_count = 0
        cover_dst = None
        if overwrite:
            desc = f'Update: {title}'
        else:
            desc = f'New:    {title}'
        for index, (link, label) in tqdm(enumerate(book), desc=desc, total=len(book)):
            content_str = requests_get(link)
            if content_str is None:
                raise Exception(f'Getting content failed: {link}')
            try:
                content_bs = BeautifulSoup(content_str.decode(encoding), 'html.parser')
            except UnicodeDecodeError as e:
                print(content_str[max(e.start - 16, 0):e.end + 15])
                raise
            content_tag = content_bs.find('div', id='content')
            contentdp = content_tag.find_all('ul', id='contentdp')
            for _tag in contentdp:
                _tag.clear()
                _tag.name = 'div'
                del _tag['id']
            image_tags = content_tag.find_all('div', class_='divimage')
            for image in image_tags:
                a = image.find('a')
                img = image.find('img')
                img_link = img.attrs['src']
                img_file = f'temp/{file_escape(img_link)}'
                img_id = f'image{img_count}'
                img_ext = ext(img_link)
                img_dst = f'{img_id}.{img_ext}'
                if cover_dst is None:
                    cover_dst = f'cover.{img_ext}'
                if not os.path.isfile(img_file):
                    img_content = requests_get(img_link)
                    if img_content is None:
                        raise Exception(f'Getting image failed: {img_link}')
                    with open(img_file, 'wb') as f:
                        f.write(img_content)
                a.name = 'p'
                a.attrs = {'style': 'text-indent:0em'}
                img.attrs = {'src': 'images/' + img_dst}
                img_count += 1
                images.append((img_id, img_file, img_dst))
            page_id = f'page{index}'
            page_title = label
            page_content = str(content_tag)
            contents.append((page_id, page_title, page_content))
        _epub = Epub(title, author=None)
        for id_, src, dst in images:
            _epub.add_image(id_, src, dst)
        for id_, page_title, page_content in contents:
            _epub.add_page(id_, page_title, page_content)
        if cover_dst is not None:
            _epub.add_cover(images[0][1], cover_dst)
            _epub.add_cover_page('cover', '', Page.cover(cover_dst, 'cover.html', _epub.metadata, ''))
        _epub.generate(epub_file, remove=True, path=path)

def search(title, page=1):
    encoding = 'GB18030'
    quoted_title = urllib.parse.quote(title)
    if not isinstance(page, int) or page < 1:
        page = 1
    link = f'https://www.wenku8.net/modules/article/search.php?searchtype=articlename&searchkey={quoted_title}&page={page}'

    page_response = requests.get(link, allow_redirects=False)
    if page_response.is_redirect:
        next_url = page_response.next.url
        m = re.search(r'book/([0-9]+).htm', next_url)
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

            book_info_tag = page.find('div', id='content')
            recommendations = book_info_tag.find('div', class_='main')
            recommendations.decompose()

            title_tag = book_info_tag.find('span', style='font-size:16px; font-weight: bold; line-height: 150%').find('b')
            title = title_tag.text

            author_tag = book_info_tag.find('table', width='100%', border='0', cellspacing='0', cellpadding='3') \
                            .find('tbody').find_all('td', width='20%')[1]
            author = author_tag.text

            cover_tag = book_info_tag.find('img')
            cover_link = cover_tag.attrs['src']

            desc_tag = page.find('td', width='48%', valign='top').find_all('span', style='font-size:14px;')[-1]
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

    total_items = None

    current_page = None
    total_pages = None
    total_pages_tag = page.find('div', id='pagelink')
    if total_pages_tag:
        total_pages_text = total_pages_tag.find('em', id='pagestats').text
        m = re.search(r' *([0-9]+) */ *([0-9]+) *', total_pages_text)
        if m:
            current_page, total_pages = int(m.group(1)), int(m.group(2))

    all_items_tag = page.find('table', class_='grid')
    item_tags = all_items_tag.find('td').children

    items = []
    for item_tag in item_tags:
        info_tag = item_tag.find('div', style='margin-top:2px;')
        title_tag = info_tag.find('a', style='font-size:13px;')
        title = title_tag.text

        book_id_text = title_tag.attrs['href']
        m = re.search(r'book/([0-9]+).htm', book_id_text)
        if m:
            book_id = int(m.group(1))
        else:
            book_id = None
        infos = info_tag.find_all('p')
        author_tag = infos[0]
        author = author_tag.text
        m = re.search(r'作者:([^/]*)/', author)
        if m:
            author = m.group(1)
        cover_tag = item_tag.find('img')
        cover_link = cover_tag.attrs['src']
        desc_tag = infos[3]
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
