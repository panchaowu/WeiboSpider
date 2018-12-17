#!/usr/bin/env python
# encoding: utf-8
import re
from lxml import etree
from scrapy import Spider
from scrapy.crawler import CrawlerProcess
from scrapy.selector import Selector
from scrapy.http import Request
from scrapy.utils.project import get_project_settings
from sina.spiders.utils import time_fix
import time
from sina.items import TweetsItem, InformationItem, RelationshipsItem, CommentItem


class WeiboSpider(Spider):
    name = "keyword"
    base_url = "https://weibo.cn"

    def start_requests(self):
        start_keywords = [
            '四川宜宾地震'
        ]
        for keyword in start_keywords:
            yield Request(url="https://weibo.cn/search/mblog?keyword={}&sort=hot&page=1".format(keyword),
                          callback=self.parse_tweet)

    def parse_tweet(self, response):
        if response.url.endswith('page=1'):
            # 如果是第1页，一次性获取后面的所有页
            all_page = re.search(r'/>&nbsp;1/(\d+)页</div>', response.text)
            if all_page:
                all_page = all_page.group(1)
                all_page = int(all_page)
                for page_num in range(2, all_page + 1):
                    page_url = response.url.replace('page=1', 'page={}'.format(page_num))
                    yield Request(page_url, self.parse_tweet, dont_filter=True, meta=response.meta)
        """
        解析本页的数据
        """
        tree_node = etree.HTML(response.body)
        tweet_nodes = tree_node.xpath('//div[@class="c" and @id]')
        for tweet_node in tweet_nodes:
            # try:
                tweet_item = TweetsItem()
                tweet_item['crawl_time'] = int(time.time())
                tweet_repost_url = tweet_node.xpath('.//a[contains(text(),"转发[")]/@href')[0]
                user_tweet_id = re.search(r'/repost/(.*?)\?uid=(\d+)', tweet_repost_url)
                tweet_item['weibo_url'] = 'https://weibo.com/{}/{}'.format(user_tweet_id.group(2),
                                                                           user_tweet_id.group(1))
                tweet_item['user_id'] = user_tweet_id.group(2)
                tweet_item['_id'] = '{}_{}'.format(user_tweet_id.group(2), user_tweet_id.group(1))
                create_time_info = tweet_node.xpath('//div/span[@class="ct" and contains(text(),"来自")]/text()')[0]
                tweet_item['created_at'] = time_fix(create_time_info.split('来自')[0].strip())

                like_num = tweet_node.xpath('.//a[contains(text(),"赞[")]/text()')[0]
                tweet_item['like_num'] = int(re.search('\d+', like_num).group())

                repost_num = tweet_node.xpath('.//a[contains(text(),"转发[")]/text()')[0]
                tweet_item['repost_num'] = int(re.search('\d+', repost_num).group())

                comment_num = \
                tweet_node.xpath('.//a[contains(text(),"评论[") and not(contains(text(),"原文"))]/text()')[0]
                tweet_item['comment_num'] = int(re.search('\d+', comment_num).group())

                tweet_content_node = tweet_node.xpath('.//span[@class="ctt"]')[0]


                # 检测由没有阅读全文:
                all_content_link = tweet_content_node.xpath('.//a[text()="全文"]')
                if all_content_link:
                    all_content_url = self.base_url + all_content_link[0].xpath('./@href')[0]
                    yield Request(all_content_url, callback=self.parse_all_content, meta={'item': tweet_item},priority=1)

                else:
                    all_content = tweet_content_node.xpath('string(.)').strip('\u200b')
                    tweet_item['content'] = all_content
                    yield tweet_item

                # 抓取该微博的评论信息
                comment_url = self.base_url + '/comment/' + tweet_item['weibo_url'].split('/')[-1] + '?page=1'
                yield Request(url=comment_url, callback=self.parse_comment, meta={'weibo_url': tweet_item['weibo_url']})

            # except Exception as e:
            #     self.logger.error(e)

    def parse_all_content(self, response):
        # 有阅读全文的情况，获取全文
        tree_node = etree.HTML(response.body)
        tweet_item = response.meta['item']
        content_node = tree_node.xpath('//div[@id="M_"]//span[@class="ctt"]')[0]
        all_content = content_node.xpath('string(.)').strip('\u200b')
        tweet_item['content'] = all_content
        yield tweet_item


    def parse_comment(self, response):
        # 如果是第1页，一次性获取后面的所有页
        if response.url.endswith('page=1'):
            all_page = re.search(r'/>&nbsp;1/(\d+)页</div>', response.text)
            if all_page:
                all_page = all_page.group(1)
                all_page = int(all_page)
                for page_num in range(2, all_page + 1):
                    page_url = response.url.replace('page=1', 'page={}'.format(page_num))
                    yield Request(page_url, self.parse_comment, dont_filter=True, meta=response.meta)
        selector = Selector(response)
        comment_nodes = selector.xpath('//div[@class="c" and contains(@id,"C_")]')
        for comment_node in comment_nodes:
            comment_user_url = comment_node.xpath('.//a[contains(@href,"/u/")]/@href').extract_first()
            if not comment_user_url:
                continue
            comment_item = CommentItem()
            comment_item['crawl_time'] = int(time.time())
            comment_item['weibo_url'] = response.meta['weibo_url']
            comment_item['comment_user_id'] = re.search(r'/u/(\d+)', comment_user_url).group(1)
            comment_item['content'] = comment_node.xpath('.//span[@class="ctt"]').xpath('string(.)').extract_first()
            comment_item['_id'] = comment_node.xpath('./@id').extract_first()
            created_at = comment_node.xpath('.//span[@class="ct"]/text()').extract_first()
            comment_item['created_at'] = time_fix(created_at.split('\xa0')[0])
            yield comment_item


if __name__ == "__main__":
    process = CrawlerProcess(get_project_settings())
    process.crawl('keyword_spider')
    process.start()