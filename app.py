import sys
import feedparser
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, Response
import requests
from bs4 import BeautifulSoup
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger()

# Global variables to store the latest RSS feeds
latest_imdb_rss = ""
latest_mlive_rss = ""

# IMDb Scraper
IMDB_URL = "https://www.imdb.com/calendar/?region=US&type=MOVIE"
def scrape_imdb():
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(IMDB_URL, headers=headers)
    if response.status_code != 200:
        logger.error(f"Failed to fetch IMDb page: {response.status_code}")
        return ""
    
    soup = BeautifulSoup(response.text, 'html.parser')
    articles = soup.find_all('article')
    
    feed_items = []
    for article in articles:
        title_tag = article.find('a')
        title = title_tag.text.strip() if title_tag else "No Title"
        link = title_tag['href'] if title_tag and title_tag.has_attr('href') else "#"
        description = article.find('span').text.strip() if article.find('span') else "No Description"
        image_tag = article.find('img')
        image_url = image_tag['src'] if image_tag and image_tag.has_attr('src') else ""
        feed_items.append({'title': title, 'link': link, 'description': description, 'image': image_url})
    
    return generate_rss("IMDB Movies", IMDB_URL, "Upcoming releases.", feed_items)

# MLive RSS Filter
MLIVE_RSS_URL = "https://www.mlive.com/arc/outboundfeeds/rss/?outputType=xml"
FILTER_KEYWORDS = {"sports", "shopping", "highschoolsports", "basketball", "baseball"}

def clean_text(text):
    return re.sub(r"[^a-zA-Z0-9\s]", "", text)

def filter_mlive():
    feed = feedparser.parse(MLIVE_RSS_URL)
    if not feed.entries:
        logger.warning("No entries found in MLive RSS feed.")
        return ""
    
    feed_items = []
    for entry in feed.entries:
        title = clean_text(entry.title)
        link = entry.link if "link" in entry else ""
        if any(keyword.lower() in title.lower() or keyword.lower() in link.lower() for keyword in FILTER_KEYWORDS):
            continue
        description = clean_text(entry.description)
        image_url = entry.media_content[0]["url"] if "media_content" in entry and entry.media_content else ""
        feed_items.append({'title': title, 'link': link, 'description': description, 'image': image_url})
    
    return generate_rss("mlive.com", MLIVE_RSS_URL, "Michigan live news feed.", feed_items)

# Generate RSS Feed XML
def generate_rss(title, link, description, items):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = link
    ET.SubElement(channel, "description").text = description
    ET.SubElement(channel, "lastBuildDate").text = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    for item in items:
        item_element = ET.SubElement(channel, "item")
        ET.SubElement(item_element, "title").text = item['title']
        ET.SubElement(item_element, "link").text = item['link']
        ET.SubElement(item_element, "description").text = item['description']
        if item['image']:
            ET.SubElement(item_element, "enclosure", url=item['image'], type="image/jpeg")
    
    return ET.tostring(rss, encoding="utf-8", method="xml").decode("utf-8")

# Flask Routes
@app.route("/imdb")
def imdb_feed():
    return Response(latest_imdb_rss, mimetype='application/rss+xml')

@app.route("/mlive")
def mlive_feed():
    return Response(latest_mlive_rss, mimetype='application/rss+xml')

# Update Feeds
scheduler = BackgroundScheduler()
def update_feeds():
    global latest_imdb_rss, latest_mlive_rss
    latest_imdb_rss = scrape_imdb()
    latest_mlive_rss = filter_mlive()
    logger.info("Feeds updated.")

scheduler.add_job(update_feeds, 'interval', hours=24)
scheduler.start()

# Initial feed update
update_feeds()

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=8080)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
