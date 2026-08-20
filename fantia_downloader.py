#!/usr/bin/env python3
"""Fantia downloader for media visible to the supplied account."""
import argparse, json, logging, mimetypes, os, re, shutil, subprocess, time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse
import requests, schedule
from bs4 import BeautifulSoup
BASE="https://fantia.jp"; CONTROL=re.compile(r'[\x00-\x1f]')
FULLWIDTH=str.maketrans({'<':'＜','>':'＞',':':'：','"':'＂','/':'／','\\':'＼','|':'｜','?':'？','*':'＊'})
EXTS={".jpg",".jpeg",".png",".gif",".webp",".bmp",".mp4",".mov",".webm",".mkv",".m4v",".zip"}
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s",handlers=[logging.FileHandler("fantia_downloader.log",encoding="utf-8"),logging.StreamHandler()])
def safe(s,f): return CONTROL.sub("_",str(s).translate(FULLWIDTH)).strip(" .")[:150] or f
def uniq(xs): return list(dict.fromkeys(x for x in xs if x))
class FantiaDownloader:
 def __init__(self,session,root,delay=1):
  self.root=Path(root).expanduser().resolve(); self.delay=delay; self.s=requests.Session(); self.filename_hints={}
  self.s.headers.update({"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36","Referer":BASE+"/"})
  for n in ("_session_id","session_id"): self.s.cookies.set(n,session,domain="fantia.jp")
 def get(self,url,**kw):
  r=self.s.get(url,timeout=60,**kw); r.raise_for_status(); return r
 def verify(self):
  r=self.get(BASE+"/mypage")
  if "/sessions/signin" in r.url or ("ログイン" in r.text and "ログアウト" not in r.text): raise RuntimeError("登录失败：请重新复制 Fantia Cookie 中的 _session_id")
 def csrf(self,soup):
  node=soup.select_one('meta[name="csrf-token"]')
  return node.get("content","") if node else ""
 def club_name(self,cid):
  s=BeautifulSoup(self.get(f"{BASE}/fanclubs/{cid}").text,"html.parser"); gtm=s.select_one("script.gtm-json")
  if gtm:
   try:
    exact=json.loads(gtm.string or "").get("fanclub_name")
    if exact:return safe(exact,cid)
   except json.JSONDecodeError:pass
  n=s.select_one("h1.fanclub-name a,.fanclub-name,.fanclubs-introduction .title,h1")
  return safe(n.get_text(" ",strip=True) if n else cid,cid)
 def posts(self,cid,since=None):
  out={}; page=1
  while True:
   soup=BeautifulSoup(self.get(f"{BASE}/fanclubs/{cid}/posts",params={"page":page}).text,"html.parser"); ids=[]; stop=False
   for a in soup.select('a[href*="/posts/"]'):
    m=re.search(r"/posts/(\d+)",a.get("href",""))
    if not m or m.group(1) in out: continue
    pid=m.group(1); ids.append(pid); box=a.find_parent(class_=re.compile("post|module")) or a
    n=box.select_one(".post-title,h2,h3"); title=a.get("title") or (n.get_text(" ",strip=True) if n else f"post_{pid}")
    d=re.search(r"(20\d\d)[-/年](\d{1,2})[-/月](\d{1,2})(?:[日\sT]+(\d{1,2}):(\d{2}))?",box.get_text(" ",strip=True))
    dt=datetime(int(d[1]),int(d[2]),int(d[3]),int(d[4] or 0),int(d[5] or 0)) if d else datetime.now()
    if since and dt<since: stop=True; continue
    out[pid]={"id":pid,"url":f"{BASE}/posts/{pid}","title":safe(title,f"post_{pid}"),"date":dt}
   if not ids or stop or not soup.select_one('a[rel="next"],.pagination .next:not(.disabled)'): break
   page+=1
  return sorted(out.values(),key=lambda x:(x["date"],int(x["id"])))
 def walk(self,v,key=""):
  if isinstance(v,dict):
   for k,x in v.items(): yield from self.walk(x,str(k))
  elif isinstance(v,list):
   for x in v: yield from self.walk(x,key)
  elif isinstance(v,str) and v.startswith(("http://","https://","//")): yield key.lower(),("https:"+v if v.startswith("//") else v)
 def payload(self,p):
  soup=BeautifulSoup(self.get(p["url"]).text,"html.parser"); data={}; csrf=soup.select_one('meta[name="csrf-token"]')
  headers={"Accept":"application/json","X-Requested-With":"XMLHttpRequest"}
  if csrf:headers["X-CSRF-Token"]=csrf.get("content","")
  r=self.s.get(f'{BASE}/api/v1/posts/{p["id"]}',headers=headers,timeout=60)
  if r.ok:
   try: data=r.json()
   except ValueError: pass
  return data,soup
 def find_id(self,value,wanted):
  if isinstance(value,dict):
   if str(value.get("id",""))==str(wanted): return value
   for child in value.values():
    found=self.find_id(child,wanted)
    if found is not None:return found
  elif isinstance(value,list):
   for child in value:
    found=self.find_id(child,wanted)
    if found is not None:return found
  return None
 def media(self,data,soup):
  c=[]
  for key,url in self.walk(data):
   path=unquote(urlparse(url).path).lower()
   if any(x in key for x in ("original","download","file","movie","video")) or Path(path).suffix in EXTS or ".m3u8" in path: c.append((0 if "original" in key or "download" in key else 1,url))
  for content in soup.select(".post-content-inner:not(.is-lock) .post-content-body,.post-content-body"):
   for n in content.select("img,source,video,a[href]"):
    u=n.get("data-src") or n.get("src") or n.get("srcset") or n.get("href")
    if u and not u.startswith("blob:"):
     u=u.split()[0]
     # Restrict HTML fallback to post assets; avatars/reactions also use image extensions.
     if "post_content" in u or "/download/" in u or (n.name in ("video","source") and Path(urlparse(u).path).suffix.lower() in EXTS): c.append((2,urljoin(BASE,u)))
  # One photo appears as JPEG + WebP thumbnails. Keep the best-ranked URL per asset id.
  result=[]; seen=set()
  for _,u in sorted(c):
   m=re.search(r"/post_content(?:_photo)?/file/(\d+)/",urlparse(u).path)
   identity=m.group(1) if m else u
   if identity not in seen: seen.add(identity); result.append(u)
  return result
 def media_groups(self,data,soup):
  post=data.get("post",{}) if isinstance(data,dict) else {}
  api_contents=post.get("post_contents",[]) if isinstance(post,dict) else []
  if api_contents:
   groups=[]
   for index,content in enumerate(api_contents,1):
    urls=[]
    # Locked content has no usable URI. Accessible file content exposes download_uri.
    if content.get("download_uri"):
     download_url=urljoin(BASE,content["download_uri"]); urls.append(download_url)
     if content.get("filename"):self.filename_hints[download_url]=content["filename"]
    elif content.get("hls_uri"):urls.append(urljoin(BASE,content["hls_uri"]))
    for photo in content.get("post_content_photos") or []:
     variants=photo.get("url") or {}; url=variants.get("original") or variants.get("main") or variants.get("large")
     if url:
      photo_url=urljoin(BASE,url); urls.append(photo_url)
      extension=Path(urlparse(photo_url).path).suffix or ".jpg"
      if photo.get("id"):self.filename_hints[photo_url]=f'{photo["id"]}{extension}'
    if content.get("embed_url") and Path(urlparse(content["embed_url"]).path).suffix.lower() in EXTS:urls.append(content["embed_url"])
    if urls:groups.append((safe(content.get("title") or "",f"内容_{index}"),uniq(urls)))
   if groups:return groups
  groups=[]
  for index,content in enumerate(soup.select(".post-content-inner"),1):
   body=content.select_one(".post-content-body") or content
   match=re.search(r"post-content-id-(\d+)",content.get("id","")); scoped={}
   if match:scoped=self.find_id(data,match.group(1)) or {}
   title_node=content.select_one(".post-content-title,h2")
   raw_title=title_node.get_text(" ",strip=True) if title_node else ""
   if not raw_title and isinstance(scoped,dict):raw_title=scoped.get("title") or scoped.get("content_title") or ""
   title=safe(raw_title,f"内容_{index}")
   urls=self.media(scoped,BeautifulSoup(str(body),"html.parser"))
   if urls:groups.append((title,urls))
  if not groups:
   urls=self.media(data,soup)
   if urls:groups.append(("无标题",urls))
  return groups
 def product_ids(self,cid):
  ids=[]; seen=set(); page=1
  while True:
   soup=BeautifulSoup(self.get(f"{BASE}/fanclubs/{cid}/products",params={"page":page}).text,"html.parser")
   found=[]
   for a in soup.select('a[href^="/products/"]'):
    match=re.fullmatch(r"/products/(\d+)",urlparse(a.get("href","")).path)
    if match and match.group(1) not in seen:
     seen.add(match.group(1)); found.append(match.group(1)); ids.append(match.group(1))
   if not found or not soup.select_one('a[rel="next"],.pagination .next:not(.disabled)'):break
   page+=1
  return ids
 def product_info_from_soup(self,pid,soup):
  schema=None
  for node in soup.select('script[type="application/ld+json"]'):
   try:value=json.loads(node.string or "")
   except (TypeError,json.JSONDecodeError):continue
   values=value if isinstance(value,list) else [value]
   schema=next((item for item in values if isinstance(item,dict) and item.get("@type")=="Product"),None)
   if schema:break
  if not schema:return None
  offers=schema.get("offers") or {}; offers=offers if isinstance(offers,list) else [offers]
  prices=[]
  for offer in offers:
   if not isinstance(offer,dict) or "price" not in offer:continue
   try:prices.append(Decimal(str(offer["price"]).replace(",","")))
   except InvalidOperation:return None
  price_box=soup.select_one("main .product-price,.product-price")
  price_text=price_box.get_text(" ",strip=True) if price_box else ""
  download_link=soup.select_one(f'a[href="/products/{pid}/download"]')
  add_link=soup.select_one(f'a[href="/products/{pid}/add_to_cart"]')
  image=schema.get("image") or ""
  if isinstance(image,list):image=next((item for item in image if isinstance(item,str)),"")
  return {
   "id":str(pid),"title":safe(schema.get("name") or f"product_{pid}",f"product_{pid}"),
   "price":prices[0] if len(prices)==1 else None,
   "is_free":len(prices)==1 and prices[0]==0,
   "is_download":bool(download_link) or "DL商品" in price_text or "ダウンロード" in price_text,
   "owned":bool(download_link),"download_url":urljoin(BASE,download_link.get("href")) if download_link else "",
   "add_url":urljoin(BASE,add_link.get("href")) if add_link else "","thumb_url":urljoin(BASE,image) if image else "",
   "soup":soup,
  }
 def product_info(self,pid):
  response=self.get(f"{BASE}/products/{pid}")
  if "/age_confirmation" in response.url:
   logging.warning("商品 %s 需要先在 Fantia 网页完成年龄确认，已跳过",pid); return None
  return self.product_info_from_soup(pid,BeautifulSoup(response.text,"html.parser"))
 def cart(self):
  response=self.get(BASE+"/mypage/cart"); soup=BeautifulSoup(response.text,"html.parser")
  ids=[node.get("value","") for node in soup.select('input[name="product_in_cart[product_id]"]') if node.get("value")]
  return soup,ids
 def remove_cart_product(self,pid):
  soup,_=self.cart()
  for form in soup.select('form[action="/mypage/cart"]'):
   if not form.select_one(f'input[name="product_in_cart[product_id]"][value="{pid}"]'):continue
   data={node.get("name"):node.get("value","") for node in form.select("input[name]")}
   response=self.s.post(urljoin(BASE,form.get("action")),data=data,headers={"Referer":BASE+"/mypage/cart"},timeout=60)
   response.raise_for_status(); return True
  return False
 def claim_free_product(self,info):
  pid=info["id"]
  if not info["is_free"] or not info["is_download"] or not info["add_url"]:return False
  _,existing=self.cart()
  if existing:
   logging.warning("购物车不是空的，为避免误购，跳过 0 日元商品 %s",pid); return False
  added=False
  try:
   headers={"X-CSRF-Token":self.csrf(info["soup"]),"Referer":f"{BASE}/products/{pid}"}
   response=self.s.post(info["add_url"],headers=headers,timeout=60); response.raise_for_status(); added=True
   cart_soup,cart_ids=self.cart()
   if cart_ids != [pid]:raise RuntimeError(f"购物车安全检查失败：{cart_ids}")
   cart_text=" ".join(cart_soup.get_text(" ",strip=True).split())
   if not re.search(r"合計\s*\(1点\)\s*0円",cart_text):raise RuntimeError("购物车合计不是 0 日元")
   check=self.get(BASE+"/mypage/cart/check",params={"init":"1"}); check_soup=BeautifulSoup(check.text,"html.parser")
   form=check_soup.select_one('form[action="/mypage/cart/purchase"]')
   if not form:raise RuntimeError("没有找到 0 日元订单确认表单")
   form_ids=[node.get("value","") for node in form.select('input[name$="[product_id]"]')]
   if form_ids != [pid]:raise RuntimeError(f"订单商品安全检查失败：{form_ids}")
   data={node.get("name"):node.get("value","") for node in form.select("input[name]") if node.get("type") not in ("submit","checkbox")}
   data["agree_to_terms_of_service"]="true"
   result=self.s.post(urljoin(BASE,form.get("action")),data=data,headers={"Referer":check.url},timeout=60); result.raise_for_status()
   owned=self.product_info(pid)
   if not owned or not owned["owned"]:raise RuntimeError("订单提交后仍未取得商品的下载权限")
   logging.info("已领取 0 日元商品：%s",info["title"]); return owned
  except Exception:
   if added:
    try:self.remove_cart_product(pid)
    except Exception:logging.exception("清理购物车中的商品 %s 失败，请手动检查购物车",pid)
   raise
 def free_products(self,cid,club_name):
  product_ids=self.product_ids(cid); logging.info("%s: 检查 %d 个商品中的 0 日元下载商品",club_name,len(product_ids))
  for pid in product_ids:
   try:
    info=self.product_info(pid)
    if not info or not info["is_download"] or not info["is_free"]:continue
    if not info["owned"]:
     info=self.claim_free_product(info)
     if not info:continue
    folder=self.root/club_name/"商品"/f'{pid}_{info["title"]}'; folder.mkdir(parents=True,exist_ok=True)
    if info["thumb_url"]:
     extension=Path(urlparse(info["thumb_url"]).path).suffix or ".jpg"
     self.filename_hints[info["thumb_url"]]=f"###thumb-product-{pid}{extension}"
     self.download(info["thumb_url"],folder)
    existing=[path for path in folder.iterdir() if path.is_file() and not path.name.startswith("###thumb-") and ".part" not in path.name]
    if existing:
     logging.info("商品已存在，跳过：%s",info["title"]); continue
    self.download(info["download_url"],folder)
    time.sleep(self.delay)
   except Exception:logging.exception("0 日元商品 %s 处理失败",pid)
 def stamp(self,path,updated_at):
  if updated_at:
   timestamp=updated_at.timestamp(); os.utime(path,(timestamp,timestamp))
 def download(self,url,folder,num=0,updated_at=None):
  path=unquote(urlparse(url).path)
  if ".m3u8" in path:
   target=folder/"video.mp4"
   if target.exists(): self.stamp(target,updated_at); return target
   ff=shutil.which("ffmpeg")
   if not ff: logging.warning("缺少 ffmpeg，跳过 m3u8 视频"); return
   subprocess.run([ff,"-y","-headers",f"Referer: {BASE}/\r\n","-i",url,"-c","copy",str(target)],check=True); self.stamp(target,updated_at); return
  hint=self.filename_hints.get(url,""); hint=safe(Path(hint).name,"") if hint else ""
  ext=Path(hint).suffix.lower() if hint else Path(path).suffix.lower(); stem=Path(hint).stem if hint else safe(Path(path).stem,"media")
  # Known extensions can be checked before making any network request.
  if ext and re.fullmatch(r"\.[A-Za-z0-9]{1,12}",ext):
   target=folder/f"{stem}{ext}"
   if target.exists() and target.stat().st_size:self.stamp(target,updated_at); return target
  r=self.get(url,stream=True)
  disposition=r.headers.get("Content-Disposition","")
  named=re.search(r"filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)",disposition,re.I)
  original=unquote(next((x for x in named.groups() if x),"")) if named else ""
  if original:
   original=safe(Path(original).name,"media"); stem=Path(original).stem; named_ext=Path(original).suffix.lower()
   if named_ext:ext=named_ext
  elif not ext:
   final_name=Path(unquote(urlparse(r.url).path)).name
   if final_name and final_name.lower()!="download":
    stem=safe(Path(final_name).stem,"media"); ext=Path(final_name).suffix.lower()
  ext=ext if ext and re.fullmatch(r"\.[A-Za-z0-9]{1,12}",ext) else mimetypes.guess_extension(r.headers.get("Content-Type","").split(";")[0]) or ".bin"
  target=folder/f"{stem}{ext}"
  if target.exists() and target.stat().st_size:self.stamp(target,updated_at); return target
  tmp=target.with_suffix(target.suffix+".part")
  with tmp.open("wb") as f:
   for chunk in r.iter_content(1024*1024):
    if chunk:f.write(chunk)
  tmp.replace(target); self.stamp(target,updated_at); return target
 def club(self,cid,since=None):
  name=self.club_name(cid); posts=self.posts(cid,since); logging.info("%s: %d 个帖子（按时间顺序）",name,len(posts))
  for i,p in enumerate(posts,1):
   logging.info("[%d/%d] %s",i,len(posts),p["title"]); data,soup=self.payload(p); n=soup.select_one("h1.post-title,.post-show-title,main h1")
   api_post=data.get("post",{}) if isinstance(data,dict) else {}
   if api_post.get("title"):p["title"]=safe(api_post["title"],p["title"])
   elif n:p["title"]=safe(n.get_text(" ",strip=True),p["title"])
   if api_post.get("posted_at"):
    try:p["date"]=parsedate_to_datetime(api_post["posted_at"])
    except (TypeError,ValueError):pass
   t=soup.select_one("time[datetime]")
   if t:
    try:p["date"]=datetime.fromisoformat(t["datetime"].replace("Z","+00:00"))
    except ValueError:pass
   folder=self.root/name/p["date"].strftime("%Y%m")/p["title"]; folder.mkdir(parents=True,exist_ok=True); groups=self.media_groups(data,soup)
   thumb=(api_post.get("thumb") or {}) if isinstance(api_post,dict) else {}
   thumb_url=thumb.get("original") or thumb.get("main") or thumb.get("large")
   if thumb_url:
    thumb_url=urljoin(BASE,thumb_url); extension=Path(urlparse(thumb_url).path).suffix or ".jpg"
    self.filename_hints[thumb_url]=f'###thumb-{p["id"]}{extension}'
    try:self.download(thumb_url,folder,updated_at=p["date"])
    except Exception as e:logging.error("封面下载失败 %s: %s",thumb_url,e)
   for plan,urls in groups:
    plan_folder=folder/plan; plan_folder.mkdir(parents=True,exist_ok=True)
    for j,u in enumerate(urls,1):
     try:self.download(u,plan_folder,j,p["date"])
     except Exception as e:logging.error("下载失败 %s: %s",u,e)
    self.stamp(plan_folder,p["date"])
   # Posts are processed oldest-to-newest, so shared month/club folders end on the latest update.
   self.stamp(folder,p["date"]); self.stamp(folder.parent,p["date"]); self.stamp(folder.parent.parent,p["date"])
   time.sleep(self.delay)
def main():
 p=argparse.ArgumentParser(description="Fantia 自动下载器")
 p.add_argument("--config",default="config.json",help="配置文件，默认 config.json")
 p.add_argument("--session",help="临时覆盖配置中的 Session")
 p.add_argument("--clubs",nargs="+",help="临时覆盖配置中的 Club ID")
 p.add_argument("--download-root",help="临时覆盖下载目录")
 p.add_argument("--since",help="临时覆盖开始日期，YYYY-MM-DD")
 p.add_argument("--schedule",help="临时覆盖每天运行时间，HH:MM")
 p.add_argument("--delay",type=float,help="临时覆盖请求间隔秒数")
 p.add_argument("--free-products",action=argparse.BooleanOptionalAction,default=None,help="自动领取并下载 Club 内价格严格为 0 日元的下载商品")
 a=p.parse_args(); config_path=Path(a.config).expanduser().resolve()
 config={}
 if config_path.exists():
  try:config=json.loads(config_path.read_text(encoding="utf-8-sig"))
  except (OSError,json.JSONDecodeError) as e:raise SystemExit(f"无法读取配置文件 {config_path}: {e}")
 session=a.session or config.get("session","")
 if not session and config.get("session_file"):
  session_path=(config_path.parent/config["session_file"]).resolve()
  try:session=session_path.read_text(encoding="utf-8-sig").strip()
  except OSError as e:raise SystemExit(f"无法读取 Session 文件 {session_path}: {e}")
 if not session or session.startswith("请把") or session.startswith("PUT_"):raise SystemExit("请先把 Fantia 的 _session_id 填入 session.txt")
 clubs=a.clubs or []
 if not clubs and config.get("club_file"):
  club_path=(config_path.parent/config["club_file"]).resolve()
  try:
   clubs=[line.strip() for line in club_path.read_text(encoding="utf-8-sig").splitlines() if line.strip() and not line.lstrip().startswith("#")]
  except OSError as e:raise SystemExit(f"无法读取 Club 文件 {club_path}: {e}")
 if not clubs:clubs=config.get("clubs") or []
 if not clubs:raise SystemExit("请在 clubs.txt 中填写至少一个 Club ID")
 root=a.download_root or config.get("download_root","FantiaDownload")
 delay=a.delay if a.delay is not None else float(config.get("delay",1))
 download_free_products=a.free_products if a.free_products is not None else bool(config.get("download_free_products",False))
 schedule_at=a.schedule if a.schedule is not None else config.get("schedule")
 since_text=a.since or config.get("since")
 since_days=int(config.get("since_days",7))
 d=FantiaDownloader(session,root,delay); d.verify()
 since=datetime.strptime(since_text,"%Y-%m-%d") if since_text else datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=since_days)
 def run():
  for cid in clubs:
   try:d.club(cid,since)
   except Exception:logging.exception("Club %s 下载失败",cid)
   if download_free_products:
    try:d.free_products(cid,d.club_name(cid))
    except Exception:logging.exception("Club %s 的 0 日元商品下载失败",cid)
 if schedule_at:
  schedule.every().day.at(schedule_at).do(run); logging.info("每天 %s 自动运行",schedule_at); run()
  while True:schedule.run_pending();time.sleep(30)
 else:run()
if __name__=="__main__":main()
