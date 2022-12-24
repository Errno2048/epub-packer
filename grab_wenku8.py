import epub

import os
import requests
import re
from tqdm import tqdm
from bs4 import BeautifulSoup

def file_escape(s):
    return re.sub(r'[\t:/\\*?<>|"\']', r'_', s)

def ext(path: str) -> str:
    rf = path.rfind(os.extsep)
    if rf >= 0:
        return path[rf + 1:]
    return ""

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36 Edg/99.0.1150.30'}

def requests_get(url, retry=10):
    count = 0
    while count < retry:
        try:
            res = requests.get(url, headers=HEADERS)
            if res.status_code >= 200 and res.status_code < 300:
                return res.content
        except Exception as e:
            pass
        count += 1
    return None

def grab(postfix, reverse=False, skip=True, path='out_wenku8'):
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
        if _skip and os.path.isfile(f'{path}/{epub_file}.epub'):
            continue
        contents = []
        images = []
        img_count = 0
        cover_dst = None
        for index, (link, label) in tqdm(enumerate(book), desc=title, total=len(book)):
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
        _epub = epub.Epub(title, author=None)
        for id_, src, dst in images:
            _epub.add_image(id_, src, dst)
        for id_, page_title, page_content in contents:
            _epub.add_page(id_, page_title, page_content)
        if cover_dst is not None:
            _epub.add_cover(images[0][1], cover_dst)
            _epub.add_cover_page('cover', '', epub.Page.cover(cover_dst, 'cover.html', _epub.metadata, ''))
        _epub.generate(epub_file, remove=True, path=path)

if __name__ == '__main__':
    pass
