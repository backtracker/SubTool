#!/usr/bin/env python
# -*- coding: utf-8 -*-'
import requests
from lxml import etree
import wget
import zipfile
from unrar import rarfile
import platform
import os
import re
import copy
import time
import urllib.parse
import configparser
import logging
import socket

global db
global base_url
movie_root_dir_list = []
movie_file_suffixes_list = []
movie_exclude_file_list = []
movie_search_keyword_exclude_regex_list = []

movie_list = []         # 遍历后得到的电影list
movie_parsed_list = []     # 解析后过滤得到的电影list
un_download_sub_movie_list = []      # 未下载过字幕的电影list

# 配置日志文件和日志级别
t = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
logging.basicConfig(filename='log/SubTool_'+t+'.log', level=logging.INFO)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)
log = logging.getLogger('SubTool')


# 电影类
class Movie(object):
    def __init__(self, file_name, dir, is_iso_dir, movie_search_keyword):
        self.file_name = file_name
        self.dir = dir
        self.is_iso_dir = is_iso_dir
        self.movie_search_keyword = movie_search_keyword


def print_author_info():
    log.info("###########################################")
    log.info("   SubTool 电影字幕下载程序")
    log.info("   版本：   1.0")
    log.info("   作者：   backtracker              ")
    log.info("   github： github.com/backtracker/SubTool  ")
    log.info("   微博：   weibo.com/backtracker")


# 读取配置文件
def read_config():
    global db, base_url,movie_root_dir_list, movie_file_suffixes_list, movie_exclude_file_list, movie_search_keyword_exclude_regex_list,default_timeout_second
    config = configparser.ConfigParser()
    try:
        config.read('config.ini', encoding="utf-8-sig")
        db = config.get("SubTool", "db")
        base_url = config.get("SubTool", "base_url")
        movie_root_dir_list = config.get("SubTool", "movie_root_dir_list").split('||')
        timeout_seconds = config.getint("SubTool", "timeout_seconds")
        socket.setdefaulttimeout(timeout_seconds)   # 设置超时时间
        movie_file_suffixes_list = config.get("SubTool", "movie_file_suffixes_list").split('||')
        movie_exclude_file_list = config.get("SubTool", "movie_exclude_file_list").split('||')
        movie_search_keyword_exclude_regex_list = config.get("SubTool", "movie_search_keyword_exclude_regex_list").split('||')
    except Exception as e:
        log.info(u"读取config.ini配置文件失败:"+e)
        time.sleep(5)
        return


# 得到最后一个目录，用来作为BDMV电影作为文件名。或者MKV等格式电影，文件名解析失败，使用目录名进行解析
def get_last_dir(dirname):
    system = platform.system()
    if system == "Windows":
        separator = "\\"
    elif system == "Linux":
        separator = "/"
    else:
        separator = "/"
    dirname_list = dirname.split(separator)
    return dirname_list[len(dirname_list)-1]


# 判断电影文件是否需要排除
def is_need_exclude_movie(movie_file_name):
    is_need_exclude = False
    for i in range(len(movie_exclude_file_list)):
        if movie_exclude_file_list[i] in movie_file_name:
            is_need_exclude = True
    return is_need_exclude


# 得到电影名称和所在目录
def walk_dir(movie_root_dir, topdown=True):
    log.info("===========================================")
    log.info(u"开始遍历 " + movie_root_dir + " 目录......")
    for root, dirs, files in os.walk(movie_root_dir, topdown):
        for file_name in files:
            name, ext = os.path.splitext(file_name)
            if ext in movie_file_suffixes_list:
                if is_need_exclude_movie(file_name) == False:
                    log.info("------------------------------------------")
                    log.info(u"电影名称："+file_name)
                    log.info(u"电影目录: "+root)
                    movie_list.append(Movie(file_name=file_name, dir=root, is_iso_dir=False, movie_search_keyword=None))
        for name in dirs:
            # BDMV电影以根目录最后一个作为电影名称, BDMV目录作为字幕文件所在目录
            if name == "BDMV":
                log.info("------------------------------------------")
                log.info(u"蓝光原盘电影名称："+get_last_dir(root))
                log.info(u"蓝光原盘电影目录："+os.path.join(root, name))
                movie_list.append(Movie(file_name=get_last_dir(root), dir=os.path.join(root, name), is_iso_dir=True, movie_search_keyword=None))


# 根据电影名称解析出搜索关键词
def regex_match_movie_name(movie_file_name):
    movie_year_list = re.findall(r'\d{4}', movie_file_name, re.I)
    # 排除分辨率
    resolution_ratio_list = ["1080", "2160"]
    for movie_year in movie_year_list:
        if movie_year in resolution_ratio_list:
            movie_year_list.remove(movie_year)

    if len(movie_year_list) > 1:
        movie_year = movie_year_list[1]
    elif len(movie_year_list) == 1:
        movie_year = movie_year_list[0]
    else:
        raise Exception

    # 电影诞生于1888年，是路易斯·普林斯在1888年最早放映的《郎德海花园场景》
    current_year = int(time.strftime("%Y", time.localtime()))
    if int(movie_year) > current_year or int(movie_year) < 1888:
        raise Exception("电影年份错误:"+movie_year)

    movie_search_keyword_pattern = re.compile(r'^.*'+movie_year)
    movie_search_keyword = movie_search_keyword_pattern.search(movie_file_name).group(0)      # 拿到电影名称+年份
    if movie_search_keyword == movie_year:
        raise Exception

    # 排除干扰关键词
    for reg in movie_search_keyword_exclude_regex_list:
        movie_search_keyword = re.sub(reg, " ", movie_search_keyword)
    return movie_search_keyword


# 解析名目和文件名称，返回电影英文名称+年份
def parse_movie_list():
    log.info("===========================================")
    log.info("开始解析电影......")
    for i in range(len(movie_list)):
        log.info("------------------------------------------")
        movie_object = movie_list[i]
        try:
            file_name = movie_object.file_name
            movie_search_keyword = regex_match_movie_name(file_name)
            movie_object.movie_search_keyword = movie_search_keyword
            movie_parsed_list.append(movie_object)    # 匹配成功，放入解析list
            log.info(u"电影："+file_name+" 解析成功")
            log.info(u"搜索关键词："+movie_search_keyword)
        except Exception:
            log.info(file_name+u" 电影名称+年份解析失败......")
            # 如果非蓝光原盘电影，以上级目录进行解析
            if not movie_object.is_iso_dir:
                try:
                    log.info(u"使用目录："+get_last_dir(movie_object.dir)+" 进行解析......")
                    movie_search_keyword = regex_match_movie_name(get_last_dir(movie_object.dir))
                    movie_object.movie_search_keyword = movie_search_keyword
                    movie_parsed_list.append(movie_object)    # 匹配成功，放入解析list
                    log.info(u"搜索关键词："+movie_search_keyword)
                except Exception:
                    log.info(get_last_dir(movie_object.dir)+u" 电影名称+年份解析失败")


# 解压ZIP
def un_zip(zip_file, dir_name):
    log.info("解压ZIP："+zip_file)
    try:
        file = zipfile.ZipFile(zip_file, "r")
        for name in file.namelist():
            relative_path_name = name.encode('cp437').decode('gbk')  # encode失败的话表示中文不乱码
            absolute_path_name = os.path.join(dir_name, relative_path_name)
            if not os.path.exists(os.path.dirname(absolute_path_name)):
                os.makedirs(os.path.dirname(absolute_path_name))
            data = file.read(name).decode('cp437')
            if not os.path.exists(absolute_path_name):
                fo = open(absolute_path_name, "w", encoding="cp437")
                fo.write(data)
                fo.close
        file.close()
    except Exception:
        file.close()
        zip_file = zipfile.ZipFile(zip_file)
        zip_file.extractall(dir_name)


# 解压rar
def un_rar(rar_file, dir_name):
    log.info(u"\n解压RAR："+rar_file)
    rar = rarfile.RarFile(rar_file)
    rar.extractall(path=dir_name)


# 得到未下载过的电影list。如果没有db文件，全部下载，如果有db文件，排除db文件中的电影
def get_un_download_sub_movie_list():
    global un_download_sub_movie_list
    if not os.path.exists(db):
        un_download_sub_movie_list = copy.deepcopy(movie_parsed_list)
    else:
        # 得到所有已经下载过的电影关键词
        downloaded_movie_search_keywords = []
        with open(db, 'r+', encoding='utf-8') as f:
            for line in f.readlines():
                line = line.strip('\n')       # 删除\n
                downloaded_movie_search_keywords.append(line)

        log.info("===========================================")
        for i in range(len(movie_parsed_list)):
            is_downloaded = False
            movie = movie_parsed_list[i]

            for j in range(len(downloaded_movie_search_keywords)):
                if movie.movie_search_keyword == downloaded_movie_search_keywords[j]:
                    is_downloaded = True
                    log.info("------------------------------------------")
                    log.info(movie.movie_search_keyword+u" 字幕已下载")
                    break

            if not is_downloaded:
                un_download_sub_movie_list.append(movie)


# 下载电影字幕
def download_movie_sub(movie_object):
    movie_search_keyword = movie_object.movie_search_keyword
    movie_dir = movie_object.dir
    is_downloaded = False  # 字幕是否已经下载

    log.info("------------------------------------------")
    log.info(movie_search_keyword+u" 字幕下载......")
    try:
        r = requests.get(base_url+'/search?q='+movie_search_keyword)
        html = etree.HTML(r.text)
        details = html.xpath("//td[@class='first']/a/@href")        # 字幕文件所在的网页
    except Exception :
        log.info(movie_search_keyword+u" 未找到字幕")
        return

    if len(details) == 0:
        log.info(movie_search_keyword+u" 未找到字幕")
        return

    # 遍历下载字幕
    for i in range(len(details)):
        log.info(u"\n下载："+base_url+details[i])
        try:
            r = requests.get(base_url + details[i])
        except Exception:
            log.info(base_url+details[i]+u" http 请求失败")
            continue
        try:
            html = etree.HTML(r.text)
            download_short_path = html.xpath("//a[@id='down1']/@href")     # 字幕下载短地址
            sub_download_url = base_url + download_short_path[0]
        except Exception:
            log.info(base_url+details[i]+u" 获取字幕文件下载地址失败")
            continue
        try:
            sub_file_name = wget.download(sub_download_url, movie_dir)
        except Exception:
            log.info(u"\n字幕下载失败!!!")
            continue

        # 下载成功记录为True
        is_downloaded = True

        name, ext = os.path.splitext(sub_file_name)
        is_zip = zipfile.is_zipfile(sub_file_name)
        is_rar = rarfile.is_rarfile(sub_file_name)
        if is_zip:
            try:
                un_zip(sub_file_name, movie_dir)
                os.remove(sub_file_name)        # 删除zip文件
            except Exception:
                log.info(u"解压zip失败")
        elif is_rar:
            try:
                un_rar(sub_file_name, movie_dir)
                os.remove(sub_file_name)
            except Exception:
                log.info(u"解压rar失败")
        else:
            os.rename(sub_file_name, urllib.parse.unquote(sub_file_name))    # 字幕文件UrlDecode

    # 如果有下载成功的记录，将已经下载过的电影记录到db中
    if is_downloaded:
        with open(db, 'a+', encoding='utf-8') as db_file:
            db_file.write(movie_object.movie_search_keyword+'\n')


# 删除wget下载过程中的临时文件
def del_tmp_files():
    for root, dirs, files in os.walk(".", True):
        for file_name in files:
            name, ext = os.path.splitext(file_name)
            if ext == ".tmp":
                os.remove(file_name)


if __name__ == "__main__":
    print_author_info()
    read_config()
    for movie_root_dir in movie_root_dir_list:
        if os.path.isdir(movie_root_dir):
            walk_dir(movie_root_dir)    # 得到电影名称和电影目录
        else:
            log.info(movie_root_dir+u" 参数错误。请在config.ini中配置movie_root_dir_list中配置电影目录。")
            time.sleep(5)

    parse_movie_list()  # 将电影名称解析成关键词
    get_un_download_sub_movie_list()

    log.info("===========================================")
    log.info(u"开始下载字幕......")
    for i in range(len(un_download_sub_movie_list)):
        movie_object = un_download_sub_movie_list[i]
        download_movie_sub(movie_object)

    del_tmp_files()
    log.info("\n全部字幕下载完成，程序将在5s后退出......")
    log.info("###########################################")
    time.sleep(5)

