# -*- coding: UTF-8 -*-

import sys
reload(sys)
sys.setdefaultencoding( "utf-8" )

import os
import wx
import wx.gizmos
import urllib2
from urlparse import urlparse
from urlparse import urlunparse
from urlparse import parse_qs
import re
import traceback
import requests
import time
import hashlib
from urllib2 import URLError
from lxml import etree
from threading import Thread, Lock
from Queue import Queue
import win32com.client
import html2text
import shutil
from send2trash import send2trash

#global variable
global body_index, full_tree, f

OUTPUT_EVENT_ID = wx.NewId()
REENABLE_EVENT_ID = wx.NewId()


#----------------------------------------------------------------------
def EVT_REGISTER(win, id, func):
	"""Define Result Event."""
	win.Connect(-1, -1, id, func)


#----------------------------------------------------------------------
class OutputEvent(wx.PyEvent):
	"""Simple event to carry arbitrary result data."""
	def __init__(self, data):
		"""Init Result Event."""
		wx.PyEvent.__init__(self)
		self.SetEventType(OUTPUT_EVENT_ID)
		self.data = data

#----------------------------------------------------------------------
class ReenableEvent(wx.PyEvent):
	"""Simple event to carry arbitrary result data."""
	def __init__(self):
		"""Init Result Event."""
		wx.PyEvent.__init__(self)
		self.SetEventType(REENABLE_EVENT_ID)

#----------------------------------------------------------------------
class WorkerThread(Thread):
	"""Test Worker Thread Class."""
 
	#----------------------------------------------------------------------
	def __init__(self, notify_window):
		"""Init Worker Thread Class."""
		Thread.__init__(self)
		self._single_page_type = 1
		self._search_page_type = 2
		self._board_page_type = 3
		self._invalid_page_type = -1
		self._notify_window = notify_window
		self._want_abort = 0
		self._want_abort_out = 0
		self._working = 1
		self.start()	# start the thread
	
	#----------------------------------------------------------------------
	def output(self, str):
		wx.PostEvent(self._notify_window, OutputEvent(str))

	#----------------------------------------------------------------------
	def handle_single_page(self, url, category, download_html, download_image, download_txt):
		global body_index, full_tree, f
		body_index = 0
		full_tree = etree.HTML('<html><head></head><body bgcolor="#FFE7F7" topmargin="0" screen_capture_injected="true"></body></html>')
				
		self.output('处理: 第1页...')
		params = parse_qs(urlparse(url).query,True)  
		temp = {}
		page = 1

		for i in range(0, 1):
			f.push({'url': url, 'current_page': i, 'end_page': i+1})

		for i in range(0, 1):
			url, current_page, end_page, ans = f.pop()
			if isinstance(ans, URLError):
				self.output('错误: 打开地址' + url + '发生错误！')
				raise ans
			else:
				if isinstance(ans, Exception):
					raise ans

			merge_result = self.get_single_html(url, current_page, end_page, ans)
			if merge_result is not None:
				temp[merge_result.get('current_page')] = merge_result
				self.output('标题: ' + merge_result.get('topic').decode(sys.getdefaultencoding()))
				page = int(merge_result.get('page')[0])
				self.output('一共: '+ str(page+1) + '页')

		for i in range(1, page+1):
			if self._want_abort:
				self.stop()
				return
			page_url = url + '&page=' + str(i)
			f.push({'url': page_url, 'current_page': i, 'end_page': page})

		for i in range(1, page+1):
			if self._want_abort:
				self.stop()
				return
			page_url, current_page, end_page, ans = f.pop()
			if isinstance(ans, URLError):
				self.output('错误: 打开地址' + url + '时发生错误！')
				raise ans
			else:
				if isinstance(ans, Exception):
					raise ans

			merge_result = self.get_single_html(page_url, current_page, end_page, ans)
			if merge_result is not None:
				temp[merge_result.get('current_page')] = merge_result

		for i in range(0, page+1):
			if self._want_abort:
				self.stop()
				return
			if temp.get(i) is not None:
				self.merge_single_html(temp[i].get('tree'), temp[i].get('current_page'))

		for page_node in full_tree.xpath('//div[@id="pager_top" or @id="pager_bottom"]/a'):
			if self._want_abort:
				self.stop()
				return
			href = page_node.attrib['href'];
			page_url = href.replace('?','')
			_params = parse_qs(page_url,True)
			page_no = _params.get('page')[0]
			page_node.attrib['href'] = '#pager_top ' + str(int(page_no) + 1)
		
		index = 1
		for page_node in full_tree.xpath('//div[@class="pager_top"]/preceding-sibling::table[1]'):
			if self._want_abort:
				self.stop()
				return
			page_node.attrib['name']= 'pager_top ' + str(index)
			page_node.attrib['id'] = 'pager_top ' + str(index)
			index = index + 1

		subpath = os.path.join('小粉红存档', '['+params.get('board')[0 ]+ ']', category)
		path = subpath.decode(sys.getdefaultencoding())
		if not os.path.isdir(path):
			os.makedirs(path)
		
		file_name = '[' + params.get('id')[0] + ']' + temp.get(0).get('topic') 
		full_path = os.path.join(path, file_name + '.html').decode(sys.getdefaultencoding())
		txt_full_path = re.sub('html$', 'txt', full_path)
						
		if self._want_abort or temp.get(0) is None:
			self.stop()
			return None
			
		image_path = os.path.join('小粉红存档', '['+params.get('board')[0 ]+ ']', category, 'images', params.get('id')[0]).decode(sys.getdefaultencoding())
		if os.path.isfile(full_path):
			download_html = True
		
		if os.path.isdir(image_path): 
			download_image = True		
			
		if download_html and download_image:
			if not os.path.isdir(path): 
				os.makedirs(path)
			
			self.output('开始: 下载图片')
			index = 0
			image_table = {}
			suffix_table = {}
			#mime = MimeTypes()
				
			for img_node in full_tree.xpath('//img[@src]'):
				if self._want_abort:
					self.stop()
					return None
				src = img_node.get('src')
				suffix = src.split('.')[-1]
				suffix = suffix.lower()
				# mime_type = mime.guess_type(src)
				# print mime_type
				types = ('png', 'jpg', 'gif', 'jpeg', 'bmp')
				for t in types:
					suffix = re.sub(t+'?.*$',t,suffix)
				#if (mime_type[0] is None) or (not(re.match('^image/', mime_type[0])))):
				if(suffix not in types):
					self.output('警告: 丢弃不合法的图片地址 ' + src)
					image_table[src] = '-1'
					suffix_table[src] = '-1'
				else:
					suffix_table[src] = suffix
					image_table[src] = '0'
						
			#print image_path
			if not os.path.isdir(image_path):
				os.makedirs(image_path)
			
			list =[]
			for src in image_table:
				if self._want_abort:
					self.stop()
					return
				if  image_table.get(src) == '0':
					replaced_url = os.path.join('images', params.get('id')[0], hashlib.md5(src).hexdigest() + '.' + suffix_table[src])
					single_image_path = os.path.join('小粉红存档', '['+params.get('board')[0 ]+ ']', category, replaced_url).decode(sys.getdefaultencoding())
					#print single_image_path
					if os.path.isfile(single_image_path) and os.path.getsize(single_image_path) > 0:
						image_table[src] = replaced_url
					else:
						list.append(src)
						f.push({'url': src, 'current_page': replaced_url, 'end_page': suffix_table[src]})
						

			for element in list:
				if self._want_abort:
						self.stop()
						return
				src, replaced_url, suffix, ans = f.pop()
				if isinstance(ans, URLError):
					self.output('错误: 下载图片' + src + '时发生错误！')
					image_table[src] = '-1'
				else:
					if isinstance(ans, Exception):
						self.output('错误: 下载图片' + src + '时发生错误！')
						image_table[src] = '-1'
					else:
						try:
							single_image_path = os.path.join('小粉红存档', '['+params.get('board')[0]+ ']', category, replaced_url).decode(sys.getdefaultencoding())
							image_file= open(single_image_path,'wb')
							image_file.write(ans)
							image_file.close()
						except Exception as e:
							self.output(traceback.format_exc().decode(sys.getdefaultencoding()))
							image_table[src] = '-1'
							self.output('错误: 保存图片' + src + '时发生错误！')
						else:
							image_table[src] = replaced_url
							self.output('成功: 保存图片' + src)

			for img_node in full_tree.xpath('//img[@src]'):
				src = img_node.get('src')
				if not (image_table.get(src) == '-1'):
					img_node.attrib['src'] = image_table.get(src)	
			self.output('下载图片: 完毕！')
			
		
		if self._want_abort or temp.get(0) is None:
			self.stop()
			return None
			
		htmlstr = etree.tostring(full_tree, pretty_print=True)		
		if download_html:
			self.output('准备保存: ' + full_path)
			file = open(full_path, 'w')
			file.write(htmlstr)
			file.close()
			self.output('保存成功: 撒花！')
			filesize = os.path.getsize(full_path.decode(sys.getdefaultencoding()))
			if filesize < 1024*1024:
				filesize =  '%.2f'%(filesize*1.0/1024) + ' KB'
			else:
				filesize =  '%.2f'%(filesize*1.0/(1024*1024)) + ' MB'
			self.output('文件大小: ' + filesize)
			if self._notify_window.filetype_combo.GetValue() == 'html':
				self._notify_window.RefreshTreeAfterDownload(self._notify_window.dir_tree_root, '['+params.get('board')[0]+ ']', category, file_name + '.html', 0)
		
		if self._want_abort:
			self.stop()
			return
			
		if download_txt or os.path.isfile(txt_full_path):
			self.output('开始: 另存为txt')
			self.output('准备保存: ' + txt_full_path)
			file = open(txt_full_path, 'w')
			file.write(html2text.html2text(htmlstr))
			file.close()
			self.output('保存txt成功: 撒花！')
			filesize = os.path.getsize(txt_full_path.decode(sys.getdefaultencoding()))
			if filesize < 1024*1024:
				filesize =  '%.2f'%(filesize*1.0/1024) + ' KB'
			else:
				filesize =  '%.2f'%(filesize*1.0/(1024*1024)) + ' MB'
			self.output('文件大小: ' + filesize)
			if self._notify_window.filetype_combo.GetValue() == 'txt':
				self._notify_window.RefreshTreeAfterDownload(self._notify_window.dir_tree_root, '['+params.get('board')[0]+ ']', category, file_name + '.txt', 0)
				
		return 0;


	def get_single_html(self, url, current_page, end_page, content):
		if self._want_abort:
			return None
				
		code = 'gb2312'
		content = content.decode(code,'ignore')
		tree = etree.HTML(content)
		topic = 'dummy'
		max_page = 0
	
		if(current_page == 0): 
			topic = tree.xpath('/html/body/title')[0].text
			topic = re.sub(u'晋江文学城网友交流区$', '', topic)
			topic = re.sub(u'―', '', topic)
			topic = re.sub(r"[\/\\\:\*\?\"\<\>\|]",'',topic)
			topic = topic.strip(' \t\n\r')
			pager = tree.xpath('//*[@id="pager_top"]/a[last()]')
			if len(pager) > 0:
				last_page_url = tree.xpath('//*[@id="pager_top"]/a[last()]')[0].attrib['href']
				last_page_url = last_page_url.replace('?','')
				params = parse_qs(last_page_url,True)
				max_page = params.get('page')

		for adv_node in tree.xpath('/html/body/table[1]'):
			if self._want_abort:
				return None
			adv_node.insert(0, etree.fromstring('<tr height="30"></tr>'))

		for adv_node in tree.xpath('/html/body/table[2]/tr[2]'):
			if self._want_abort:
				return None
			adv_node.getparent().insert(2, etree.fromstring('<tr height="15"></tr>'))
			adv_node.getparent().remove(adv_node)

		for adv_node in tree.xpath('/html/body/center'):
			if self._want_abort:
				return None
			adv_node.getparent().remove(adv_node)

		for adv_node in tree.xpath('//td[@class="read"]/font[@color="gray"]'):
			if self._want_abort:
				return None
			adv_node.getparent().remove(adv_node)
		

		if current_page < end_page:
			for adv_node in tree.xpath('//*[@id="pager_bottom"]'):
				if self._want_abort:
					return None
				adv_node.getparent().remove(adv_node)


		index = 0
		for adv_node in tree.xpath('/html/body/table[3]/tr[position() mod 4 = 1]'):
			#adv_node.getparent().insert(4*index+1, etree.fromstring('<tr height="15"></tr>'))
			if self._want_abort:
				return None
			adv_node.getparent().remove(adv_node)
			index = index + 1

		for adv_node in tree.xpath('/html/body/*[self::form or self::p]'):
			if self._want_abort:
				return	None
			adv_node.getparent().remove(adv_node)

		for adv_node in tree.xpath('/html/*/script'):
			if self._want_abort:
				return None
			adv_node.getparent().remove(adv_node)

		for adv_node in tree.xpath('/html/body/table[position() > 3]'):
			if self._want_abort:
				return None
			adv_node.getparent().remove(adv_node)

		tree.xpath('/html/body/table[1]/tr[2]/td')[0].insert(5, etree.fromstring('<b>→ </b>'))

		url = url.replace('&', '&amp;')
		tree.xpath('/html/body/table[1]/tr[2]/td')[0].insert(5, 
		etree.fromstring('<a target="_blank" href="' + url + '">'+ '去原帖' +'</a>'))

		return {'topic': topic, 'page': max_page or ['0'], 'tree' : tree, 'current_page': current_page}


	def merge_single_html(self, tree, current_page):
		global body_index,full_tree
		if current_page == 0:
			index = 0
			for node in tree.xpath('/html/head/*'):
				if self._want_abort:
					self.stop()
					return None
				full_tree.xpath('/html/head')[0].insert(index, node)
				index = index + 1
			for node in tree.xpath('/html/body/*'):
				if self._want_abort:
					self.stop()
					return None
				if(node.tag == 'div' and node.get('id') == 'pager_top'):
					node.attrib['class'] = 'pager_top'
				full_tree.xpath('/html/body')[0].insert(body_index, node)
				body_index = body_index + 1
		else:
			for node in tree.xpath('/html/body/table[2]'):
				if self._want_abort:
					self.stop()
					return None
				node.getparent().remove(node)
			for node in tree.xpath('/html/body/div[2]'):
				if self._want_abort:
					self.stop()
					return None
				node.getparent().remove(node)

			for node in tree.xpath('/html/body/*[(self::div or self::table)]'):
				if self._want_abort:
					self.stop()
					return None

				if(node.tag == 'div' and node.get('id') == 'pager_top'):
					node.attrib['class'] = 'pager_top'
				full_tree.xpath('/html/body')[0].insert(body_index, node)
				body_index = body_index + 1

	def handle_search_n_board_page(self, url, category, download_html, download_image, download_txt):
		global f
		for i in range(0, 1):
			f.push({'url': url, 'current_page': i, 'end_page': i+1})

		ans = None
		for i in range(0, 1):
			url, current_page, end_page, ans = f.pop()
			if isinstance(ans, URLError):
				self.output('错误: 打开地址' + url + '发生错误！')
				raise ans
			else:
				if isinstance(ans, Exception):
					raise ans
					
		code = 'gb2312'
		content = ans.decode(code,'ignore')
		tree = etree.HTML(content)

		for href_node in tree.xpath('//td/a[position()=1 and starts-with(@href, "showmsg.php?board")]'):
			if self._want_abort_out:
				return
			href =  href_node.get('href')
			href = 'http://bbs.jjwxc.net/' + href
			self.output('发现链接: ' + href)
			self.main_handler(href, category, download_html, download_image, download_txt);
			self.output('')
			
	def get_url_type(self, url):
		self.output('目标: ' + url)
		category_from_url = ''
		try:
			result = urlparse(url)
			params = parse_qs(result.query,True)
		except Exception as e:
			return (self._invalid_page_type, category_from_url, url)
		
		if result.scheme != 'http' or result.netloc != 'bbs.jjwxc.net':
			return (self._invalid_page_type, category_from_url, url);
		else:
			parsed_url = list(result)
			# remove the # parameters
			for x in parsed_url[5].split('&'):
				if re.search(r'^category=(.*)$',x):
					category_from_url = re.search(r'^category=(.*)$',x).group(1)

			if result.path == '/showmsg.php':
				if params.get('board') is None or params.get('id') is None or not re.match(r'^\d+$', params.get('board')[0]) or not re.match(r'^\d+$', params.get('id')[0]):
					return (self._invalid_page_type, category_from_url, url)
				else:
					parsed_url[4] = '&'.join([x for x in parsed_url[4].split('&') if (not re.match('^page=', x) and not re.match('^keyword=', x))])
					new_url = urlunparse(parsed_url)
					return (self._single_page_type, category_from_url, new_url)
			else:
				if result.path == '/board.php':
					if params.get('board') is None or params.get('page') is None or not re.match(r'^\d+$', params.get('board')[0]) or not re.match(r'^\d+$', params.get('page')[0]):
						return (self._invalid_page_type, category_from_url, url)
					else:
						return (self._board_page_type, category_from_url, url)
				else:
					if result.path == '/search.php':
						if params.get('board') is None or not re.match(r'^\d+$', params.get('board')[0]) or (params.get('page') is not None and not re.match(r'^\d+$', params.get('page')[0])) or params.get('topic') is None or not re.match(r'^\d+$', params.get('topic')[0]) or params.get('act') is None or params.get('act')[0] != 'search' or params.get('keyword') is None:
							return (self._invalid_page_type, category_from_url, url)
						else:
							return (self._search_page_type, category_from_url, url)
					else:
						return (self._invalid_page_type, category_from_url, url)
	
		
	def main_handler(self, url, category, download_html, download_image, download_txt):
		url = url.strip(' \t\n\r')
		url = url.lower()
		if (download_html == False and download_txt == False) or url == '':
			return

		if url == '':
				return
		(type, category_from_url, url) = self.get_url_type(url)

		category = category if category_from_url == '' else category_from_url

		category = category.strip(' \t\n\r')
		category = '无分类' if category == '' else category

		if type == self._invalid_page_type:
			self.output('地址非法: ' + url)
			self.output('')
			return 0;
		
		try:		
			if type == self._single_page_type:
				self.output('类别: 帖子')
				self.handle_single_page(url, category, download_html, download_image, download_txt)
				self.output('')
			if type == self._search_page_type:
				self.output('类别: 搜索')
				self.handle_search_n_board_page(url, category, download_html, download_image, download_txt)
				self.output('')
			if type == self._board_page_type:
				self.output('类别: 版面')
				self.handle_search_n_board_page(url, category, download_html, download_image, download_txt)			
				self.output('')
		except URLError as e:
			self.output('错误: 打开地址发生错误，请检查网络连接是否畅通！')
			self.output(traceback.format_exc().decode(sys.getdefaultencoding()))
		except IOError as e:
			if e.errno == 13:
				self.output('错误: 权限不够或者该文件正在使用中，请删除后重试！')
				self.output(traceback.format_exc().decode(sys.getdefaultencoding()))
		except IndexError as e:
			self.output('错误: 网页不存在或已删除！')
			self.output(traceback.format_exc().decode(sys.getdefaultencoding()))
		except Exception as e:
			self.output(traceback.format_exc().decode(sys.getdefaultencoding()))
			pass
		if self._want_abort:
			self.stop()
	#----------------------------------------------------------------------
	def run(self):
		# clear the stop flag
		self._want_abort = 0 
		self._want_abort_out = 0
		
		if re.match(r'[\/\\\:\*\?\"\<\>\|]', self._notify_window.category_text_input.GetValue()):
			wx.MessageBox('分类中不能包含如下字符 / \ : * ? " < > |')
		else:
			# clear the exiting queue
			for i in  range(0, f.taskleft()):
				f.pop()
				
			for url in self._notify_window.input_text.GetValue().split("\n"):
				if self._want_abort_out:
					return
				self.main_handler(url, self._notify_window.category_text_input.GetValue(), self._notify_window.html_checkbox.GetValue(), self._notify_window.image_checkbox.GetValue(), self._notify_window.txt_checkbox.GetValue())
		self.recover()


	#----------------------------------------------------------------------
	def abort(self):
 		self._want_abort = 1
		self._want_abort_out = 1

	#----------------------------------------------------------------------
	def recover(self):
		wx.PostEvent(self._notify_window, ReenableEvent())
		self._want_abort = 0
		self._working = 0

		
	#----------------------------------------------------------------------
	def stop(self):
		self.recover()
		self.output('用户操作: 终止')

class Fetcher:
	def __init__(self,threads):
		self.opener = urllib2.build_opener(urllib2.HTTPHandler)
		self.lock = Lock()
		self.q_req = Queue()
		self.q_ans = Queue()
		self.threads = threads
		for i in range(threads):
			t = Thread(target=self.threadget)
			t.setDaemon(True)
			t.start()
		self.running = 0

	def __del__(self):
		time.sleep(0.5)
		self.q_req.join()
		self.q_ans.join()
 
	def taskleft(self):
		return self.q_req.qsize()+self.q_ans.qsize()+self.running 

	def push(self,req):
		self.q_req.put(req)
 
	def pop(self):
		return self.q_ans.get()
 
	def threadget(self):
		while True:
			param = self.q_req.get()
			with self.lock:
				self.running += 1
			try:
				ans = self.opener.open(param.get('url'), timeout=10).read()
			except Exception as  e:
				self.q_ans.put((param.get('url'), param.get('current_page'), param.get('end_page'), e))
			else:	
				self.q_ans.put((param.get('url'), param.get('current_page'), param.get('end_page'), ans))
			with self.lock:
				self.running -= 1
			self.q_req.task_done()
			time.sleep(0.1) # don't spam

class TreeItemData:
	def __init__(self, url, path, depth):
		self.url = url
		self.path = path
		self.depth = depth


class MainWindow(wx.Frame):
	def __init__(self, parent, id, title):
		wx.Frame.__init__(self, parent, id, title, style = wx.SYSTEM_MENU | wx.CAPTION | wx.CLOSE_BOX | wx.MINIMIZE_BOX | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER )
		self.SetBackgroundColour('#FFE7F7')
		mainSizer =  wx.BoxSizer(wx.HORIZONTAL)
		leftSizer = wx.BoxSizer(wx.VERTICAL)
		rightSizer  = wx.BoxSizer(wx.VERTICAL)
		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		checkSizer = wx.BoxSizer(wx.HORIZONTAL)
		searchSizer = wx.BoxSizer(wx.HORIZONTAL)
		
		self.input_text_label = wx.StaticText(self, -1, '支持单个帖子/搜索结果/版面三类地址↓ ↓ ↓')
		self.output_text_label = wx.StaticText(self, -1, '随便看不看的结果在这里↓ ↓ ↓')
		self.input_text = wx.TextCtrl(self, -1,  style = wx.TE_MULTILINE | wx.TE_RICH | wx.TE_PROCESS_ENTER)
		self.output_text = wx.TextCtrl(self, -1, style = wx.TE_MULTILINE | wx.TE_RICH | wx.TE_READONLY |wx.TE_PROCESS_ENTER) 

		
		self.clear_button = wx.Button(self, -1, label = '清空 ╮(╯▽╰)╭ ')
		self.confirm_button = wx.Button(self, -1, label = '存帖 ヾ(≧O≦)〃')
		self.cancel_button = wx.Button(self,-1, label= '停止(￣_,￣ )')
		self.cancel_button.Disable()
		
		self.category_text_label = wx.StaticText(self, -1, '类别: ')
		self.category_text_input = wx.TextCtrl(self, -1, value='无分类')
		self.html_checkbox = wx.CheckBox(self, -1, label='存为html')
		self.html_checkbox.SetValue(True)
		self.image_checkbox = wx.CheckBox(self, -1, label='下载图片')
		self.txt_checkbox = wx.CheckBox(self, -1, label='存为txt')
		
		self.dir_path = os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '小粉红存档').decode(sys.getdefaultencoding())
		self.search_box = wx.SearchCtrl(self, -1, style=wx.TE_PROCESS_ENTER)
		self.search_text = ''
		self.filetype_combo= wx.ComboBox(self, -1, value = "html", choices = ['html', 'txt'], style = wx.CB_DROPDOWN)
		#self.refresh_button = wx.Button(self,-1, label= '刷新所有')
		self.dir_tree = wx.TreeCtrl(self, -1, style=wx.TR_HAS_BUTTONS + wx.TR_HIDE_ROOT)
		if not os.path.isdir(self.dir_path): 
			os.makedirs(self.dir_path)
		self.PrepareOldFile(self.dir_path, 0)
		self.RecreateTree()
		self.selected_item = self.dir_tree.GetRootItem()
		self.file_popupmenu = wx.Menu()
		for text in "刷新(存贴时不可用) 打开 删除 打开原帖 移动至其他分类".split():
			item = self.file_popupmenu.Append(-1, text)
			self.Bind(wx.EVT_MENU , self.OnPopupItemSelected, item)
		self.dir_popupmenu = wx.Menu()
		for text in "打开 删除 新建分类".split():
			item = self.dir_popupmenu.Append(-1, text)
			self.Bind(wx.EVT_MENU , self.OnPopupItemSelected, item)

		leftSizer.Add(self.input_text_label, 1, wx.CENTER)
		leftSizer.Add(self.input_text, 6, wx.EXPAND)
		
		btnSizer.Add(self.clear_button,1, wx.LEFT|wx.RIGHT, border=5)
		btnSizer.Add(self.confirm_button,1, wx.LEFT|wx.RIGHT, border=5)
		btnSizer.Add(self.cancel_button,1, wx.LEFT|wx.RIGHT, border=5)

		checkSizer.Add(self.category_text_label,0, wx.LEFT, border=5)
		checkSizer.Add(self.category_text_input,0, wx.RIGHT, border=5)
		checkSizer.Add(self.html_checkbox,1, wx.LEFT|wx.RIGHT, border=5)
		checkSizer.Add(self.image_checkbox,1, wx.LEFT|wx.RIGHT, border=5)
		checkSizer.Add(self.txt_checkbox,1, wx.LEFT|wx.RIGHT, border=5)
		
		leftSizer.Add(checkSizer, 1, wx.CENTER|wx.ALL, border=3)
		leftSizer.Add(btnSizer, 1, wx.CENTER|wx.ALL, border=3)

		leftSizer.Add(self.output_text_label, 1, wx.UP|wx.CENTER, border=5)
		leftSizer.Add(self.output_text, 10, wx.EXPAND)
		
		searchSizer.Add(self.search_box, 4, wx.LEFT, border=5)
		searchSizer.Add(self.filetype_combo,1, wx.LEFT, border=10)
		#searchSizer.Add(self.refresh_button,1, wx.LEFT, border=5)
		rightSizer.Add(searchSizer, 1, wx.CENTER)
		
		rightSizer.Add(self.dir_tree, 19, wx.EXPAND)
		
		mainSizer.Add(leftSizer,1, wx.EXPAND | wx.ALL, border=5)
		mainSizer.Add(rightSizer,1, wx.EXPAND | wx.ALL, border=5)
		self.SetSizer(mainSizer)
		mainSizer.Fit(self)
		
		self.search_box.Bind(wx.EVT_TEXT, self.OnSearch)
		self.dir_tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnTreeNodeDoubleClick)
		self.dir_tree.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.OnTreeNodeRightClick)
		self.clear_button.Bind(wx.EVT_BUTTON, self.ClearText)
		self.confirm_button.Bind(wx.EVT_BUTTON, self.OnStart)
		self.cancel_button.Bind(wx.EVT_BUTTON, self.OnStop)
		self.filetype_combo.Bind(wx.EVT_COMBOBOX, self.OnFiletypeChange)
		self.html_checkbox.Bind(wx.EVT_CHECKBOX,self.OnHTMLCheck)
		#self.refresh_button.Bind(wx.EVT_CHECKBOX,self.OnRefreshAll)
		EVT_REGISTER(self, OUTPUT_EVENT_ID, self.OnOutput)
		EVT_REGISTER(self, REENABLE_EVENT_ID, self.OnEnable)
		self.worker = None


	def RefreshTreeAfterDownload(self, root, board, category, name, depth):
		root_data = self.dir_tree.GetItemData(root).GetData()
		item, cookie = self.dir_tree.GetFirstChild(self.dir_tree_root)
		item = None
		# adding category
		if root_data.depth == 0:
			item = self.InsertNode(root, board)
			self.RefreshTreeAfterDownload(item, board, category, name, depth+1)
		if root_data.depth == 1:
			item = self.InsertNode(root, category)
			self.RefreshTreeAfterDownload(item, board, category, name, depth+1)
		if root_data.depth == 2:
			self.InsertNode(root, name)
		

	def InsertNode(self, root, name):
		root_data = self.dir_tree.GetItemData(root).GetData()
		item, cookie = self.dir_tree.GetFirstChild(root)
		index = -1;
		inserted = False
		# adding category
		if root_data.depth == 1:
			data=wx.TreeItemData(TreeItemData(self.dir_tree.GetItemData(root).GetData().url + '#category='+name, name, root_data.depth+1))
		if root_data.depth == 2:
			id = re.search(r'^\[(\d+)\]',name).group(1)
			data=wx.TreeItemData(TreeItemData(self.dir_tree.GetItemData(root).GetData().url.replace('#category','&id='+id+'#category'), id, root_data.depth+1))
		while item.IsOk():
			index = index+1
			if self.dir_tree.GetItemText(item) == name:
				return item
			if self.dir_tree.GetItemText(item) > name:
				self.dir_tree.InsertItemBefore(parent=root, index=index, text=name, data=data)
				inserted=True
				break
			item, cookie = self.dir_tree.GetNextChild(root, cookie)
		if not inserted:
			self.dir_tree.AppendItem(parent=root, text=name, data=data)


	def RecreateTree(self):
		self.dir_tree.Freeze()
		self.dir_tree.DeleteAllItems()
		self.dir_tree_root = self.dir_tree.AddRoot(self.dir_path, data=wx.TreeItemData(TreeItemData('http://bbs.jjwxc.net/showmsg.php?', self.dir_path, 0)))
		self.AddItem(self.dir_tree_root, self.dir_path, 1)
		self.dir_tree.ExpandAll()
		self.dir_tree.Thaw()

	def OnHTMLCheck(self, evt):
		if not self.html_checkbox.GetValue():
			self.image_checkbox.SetValue(False)
			self.image_checkbox.Disable()
		else:
			self.image_checkbox.Enable()
			
	def OnFiletypeChange(self, evt):
		self.RecreateTree()
		
	def OnSearch(self, evt):
		search_text = self.search_box.GetValue().strip(' \t\n\r')
		if self.search_text == search_text:
			return
		else:
			self.search_text = search_text
			self.RecreateTree()

	def OnPopupItemSelected(self, evt):
		item = self.file_popupmenu.FindItemById(evt.GetId()) or self.dir_popupmenu.FindItemById(evt.GetId())
		text = item.GetText()
		data = self.dir_tree.GetItemData(self.selected_item).GetData()
		self_text = self.dir_tree.GetItemText(self.selected_item)
		if text == '删除':
			dlg = wx.MessageDialog(self, '确认真的要删除'+data.path+'吗?', '= =', wx.OK|wx.CANCEL|wx.ICON_QUESTION)
			result = dlg.ShowModal()
			dlg.Destroy()
			if result == wx.ID_OK:
				try:
					if os.path.isdir(data.path):
						send2trash(data.path)
						wx.PostEvent(self, OutputEvent('删除: ' + data.path + '成功'))
					else:
						send2trash(data.path)
						wx.PostEvent(self, OutputEvent('删除: ' + data.path + '成功'))
						id=re.search(r'^\[(\d+)\].*\.(html|txt)$',self_text).group(1)
						image_path = os.path.join(data.path,'..','images',id).decode(sys.getdefaultencoding())
						if os.path.isdir(image_path):
							send2trash(image_path)
							wx.PostEvent(self, OutputEvent('删除: ' + image_path + '成功'))
						another_path = re.sub('html$', 'txt', data.path)
						if os.path.isfile(another_path):
							send2trash(another_path)
							wx.PostEvent(self, OutputEvent('删除: ' + another_path + '成功'))
						another_path = re.sub('txt$', 'html', data.path)
						if os.path.isfile(another_path):
							send2trash(another_path)
							wx.PostEvent(self, OutputEvent('删除: ' + another_path + '成功'))						
				except Exception as e:
					wx.PostEvent(self, OutputEvent('删除: ' + data.path + '时发生错误！'))
				wx.PostEvent(self, OutputEvent(''))
				self.dir_tree.Delete(self.selected_item)
				self.dir_tree.UnselectAll()
		else:
			if text == '打开':
				try:
					os.startfile(data.path)
				except Exception as e:
					wx.PostEvent(self, OutputEvent('打开: ' + data.path + '时发生错误！'))
				else:
					wx.PostEvent(self, OutputEvent('打开: ' + data.path + '成功'))
				wx.PostEvent(self, OutputEvent(''))
			else: 
				if text == '新建分类':
					dlg = wx.TextEntryDialog(self, '请输入新建分类的名字','= =', 'Python')
					dlg.SetValue('无分类')
					if dlg.ShowModal() == wx.ID_OK:
		   				new_category = dlg.GetValue()
						new_category = new_category.strip(' \t\n\r')
						if new_category == '' or re.match(r'[\/\\\:\*\?\"\<\>\|]', new_category) :
							wx.MessageBox('新建分类不能为空且不能包含如下字符 / \ : * ? " < > |' )
						else:
							self.InsertNode(self.selected_item, new_category)
				else:
					if text == '打开原帖':
						try:
							os.startfile(url)
						except Exception as e:
							wx.PostEvent(self, OutputEvent('打开: ' + data.url + '时发生错误！'))
						else:
							wx.PostEvent(self, OutputEvent('打开: ' + data.url + '成功'))
						wx.PostEvent(self, OutputEvent(''))
					else:
						if text == '刷新(存贴时不可用)':
							self.input_text.SetValue(data.url)
							self.html_checkbox.SetValue(self.filetype_combo.GetValue()=='html')
							self.txt_checkbox.SetValue(self.filetype_combo.GetValue()=='txt')
							wx.PostEvent(self.confirm_button, wx.PyCommandEvent(wx.EVT_BUTTON.typeId, self.confirm_button.GetId()))



	def OnTreeNodeRightClick(self, evt):
		self.selected_item = evt.GetItem()
		data = self.dir_tree.GetItemData(self.selected_item).GetData()
		if data.depth < 3:
			if self.dir_tree.GetItemParent(self.selected_item) != self.dir_tree_root:
				self.dir_popupmenu.GetMenuItems()[2].Enable(False)
			else:
				self.dir_popupmenu.GetMenuItems()[2].Enable(True)
			self.PopupMenu(self.dir_popupmenu)
		else:
			for item in self.file_popupmenu.GetMenuItems():
				if item.GetText() == '刷新(存贴时不可用)':
					item.Enable(self.worker is None or self.worker._working == 0)
			self.PopupMenu(self.file_popupmenu)

	def GetCurrentPath(self, item):
		if item == self.dir_tree.GetRootItem():
			return self.dir_path
		else:
			return os.path.join(self.GetCurrentPath(self.dir_tree.GetItemParent(item)), self.dir_tree.GetItemText(item))

	def PrepareOldFile(self, path, depth):
		for i in os.listdir(path):
			tmpdir = os.path.join(path,i)
			if os.path.isdir(tmpdir) and depth == 0:
				id = re.sub(']$', '', re.sub('^\[', '', i))
				if not re.match(r'^\d+$', id):
					self.PrepareOldFile(tmpdir,depth+1)
			if depth == 1 and (os.path.isfile(tmpdir) and re.match(r'^\[\d+\].*\.(html|txt)$',i) or os.path.isdir(tmpdir) and i == 'images'):
				uncatedir = os.path.join(path, '无分类')
				if not os.path.isdir(uncatedir):
					os.makedirs(uncatedir)
					wx.PostEvent(self, OutputEvent('创建: ' + uncatedir))
				if os.path.isfile(tmpdir):
					if os.path.exists(os.path.join(uncatedir, i)):
						send2trash(os.path.join(uncatedir, i))
					shutil.move(tmpdir, os.path.join(uncatedir, i))
					wx.PostEvent(self, OutputEvent('移动: ' + tmpdir + ' -> ' + os.path.join(uncatedir, i)))
				else:
					for subfolder in os.listdir(tmpdir):
						childdir = os.path.join(tmpdir, subfolder)
						print childdir
						if os.path.isdir(childdir):
							if os.path.exists(os.path.join(uncatedir, i)):
								send2trash(os.path.join(uncatedir, i))
								os.makedirs(os.path.join(uncatedir,i))
							shutil.move(childdir, os.path.join(uncatedir, i))
							wx.PostEvent(self, OutputEvent('移动: ' + childdir + ' -> ' + os.path.join(uncatedir, i)))
					if len(os.listdir(tmpdir)) == 0:
						wx.PostEvent(self, OutputEvent('删除空文件夹: ' + tmpdir))
						send2trash(tmpdir)



	def AddItem(self,root,path,depth):
		for i in os.listdir(path):
			tmpdir = os.path.join(path,i)
			if os.path.isdir(tmpdir):
				if depth == 1:
					if re.match(r'^\[\d+\]$', i):
						id = re.search(r'^\[(\d+)\]$',i).group(1)
						child = self.dir_tree.AppendItem(parent = root, text = i, data=wx.TreeItemData(TreeItemData(self.dir_tree.GetItemData(root).GetData().url + 'board='+id, tmpdir, depth)))
						self.AddItem(child,tmpdir,depth+1)
				if depth == 2 and i != 'images':
					child = self.dir_tree.AppendItem(parent = root, text = i, data=wx.TreeItemData(TreeItemData(self.dir_tree.GetItemData(root).GetData().url + '#category='+i, tmpdir, depth)))
					self.AddItem(child,tmpdir,depth+1)
			else:
				if depth == 3 and os.path.isfile(tmpdir) and re.match(r'^\[\d+\].*\.'+self.filetype_combo.GetValue()+'$',i) and self.search_text.lower() in i.lower():
					id = re.search(r'^\[(\d+)\]',i).group(1)
					child = self.dir_tree.AppendItem(parent = root, text = i, data=wx.TreeItemData(TreeItemData(self.dir_tree.GetItemData(root).GetData().url.replace('#category','&id='+id+'#category'), tmpdir, depth)))

	def RemoveItem(self,root,path):
		pass

	def ClearText(self, evt):
		self.input_text.Clear()
		self.output_text.Clear()


	def OnTreeNodeDoubleClick(self, evt):
		item = evt.GetItem()
		path =  self.GetCurrentPath(item)
		os.startfile(path)

	def OnStart(self, evt):
		self.input_text.Disable()
		self.clear_button.Disable()
		self.confirm_button.Disable()
		self.cancel_button.Enable()
		self.html_checkbox.Disable()
		self.image_checkbox.Disable()
		self.txt_checkbox.Disable()
		#self.refresh_button.Disable()
		self.worker = WorkerThread(self)
	
	def OnStop(self, evt):
		self.cancel_button.Disable()
		if self.worker:
			self.worker.abort()

	def OnOutput(self, evt):
		self.output_text.AppendText(evt.data.decode(sys.getdefaultencoding()))
		self.output_text.AppendText("\n")


	def OnEnable(self, evt):
		self.input_text.Enable()
		self.clear_button.Enable()
		self.confirm_button.Enable()
		self.cancel_button.Disable()
		self.html_checkbox.Enable()
		self.image_checkbox.Enable()
		self.txt_checkbox.Enable()
		#self.refresh_button.Enable();
		
	def OnSize(self, evt):
		if self.GetAutoLayout():
			self.Layout()


class MainApp(wx.App):
	"""Class Main App."""
	def OnInit(self):
		"""Init Main App."""
		frame = MainWindow( None, -1, '小粉红存贴助手(有bug指路board=3&id=727804)')
		frame.Show(True)
		return True
		
if __name__=='__main__':
	global f
	f = Fetcher(threads=10)
	app = MainApp(0)
	proc_name = sys.argv[0]
	proc_name = proc_name.split('\\')[-1]
	#print proc_name
	my_pid = os.getpid()

	wmi = win32com.client.GetObject('winmgmts:')
	all_procs = wmi.InstancesOf('Win32_Process')

	for proc in all_procs:
		if proc.Properties_("Name").Value == proc_name:
			proc_pid = proc.Properties_("ProcessID").Value
			if proc_pid != my_pid:
				os.kill(proc_pid, 9)
	app.MainLoop()
	