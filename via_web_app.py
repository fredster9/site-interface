"""
Via Web App - Personalized Content Interface
============================================
A Streamlit web app for ridewithvia.com that provides:
1. User profile collection (city/agency, state)
2. LLM-powered chat interface for website content
3. Personalized article recommendations
4. Q&A logging to Google Sheets (permanent) or CSV file (fallback)
"""

import streamlit as st
import json
import os
import re
import numpy as np
import random
from typing import Dict, List, Optional
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import pandas as pd
from openai import OpenAI
import logging

# Google Sheets imports
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

# ============================================================================
# CONFIGURATION
# ============================================================================

WEBSITE_URL = 'https://ridewithvia.com'
CONTENT_CACHE_FILE = 'via_website_content.json'
EMBEDDING_MODEL = 'text-embedding-3-small'  # Fast and cost-effective
GOOGLE_SHEETS_SPREADSHEET_ID = '1Qu26woHPnzzPcKUEY-_0QkORM5AZM2PGM38qB2FWpu4'  # Default spreadsheet ID
GOOGLE_SHEETS_SHEET_NAME = 'Q&A Log'  # Default sheet name
QA_LOG_FILE = 'qa_log.csv'  # CSV log file for Q&A pairs

# State coordinates for distance calculation (approximate centers)
STATE_COORDINATES = {
    'AL': (32.806671, -86.791130), 'AK': (61.370716, -152.404419), 'AZ': (33.729759, -111.431221),
    'AR': (34.969704, -92.373123), 'CA': (36.116203, -119.681564), 'CO': (39.059811, -105.311104),
    'CT': (41.597782, -72.755371), 'DE': (39.318523, -75.507141), 'FL': (27.766279, -81.686783),
    'GA': (33.040619, -83.643074), 'HI': (21.094318, -157.498337), 'ID': (44.240459, -114.478828),
    'IL': (40.349457, -88.986137), 'IN': (39.849426, -86.258278), 'IA': (42.011539, -93.210526),
    'KS': (38.526600, -96.726486), 'KY': (37.668140, -84.670067), 'LA': (31.169546, -91.867805),
    'ME': (44.323535, -69.765261), 'MD': (39.063946, -76.802101), 'MA': (42.230171, -71.530106),
    'MI': (43.326618, -84.536095), 'MN': (45.694454, -93.900192), 'MS': (32.741646, -89.678696),
    'MO': (38.572954, -92.189283), 'MT': (46.921925, -110.454353), 'NE': (41.125370, -98.268082),
    'NV': (38.313515, -117.055374), 'NH': (43.452492, -71.563896), 'NJ': (40.298904, -74.521011),
    'NM': (34.840515, -106.248482), 'NY': (42.165726, -74.948051), 'NC': (35.630066, -79.806419),
    'ND': (47.528912, -99.784012), 'OH': (40.388783, -82.764915), 'OK': (35.565342, -96.928917),
    'OR': (44.572021, -122.070938), 'PA': (40.590752, -77.209755), 'RI': (41.680893, -71.51178),
    'SC': (33.856892, -80.945007), 'SD': (44.299782, -99.438828), 'TN': (35.747845, -86.692345),
    'TX': (31.054487, -97.563461), 'UT': (40.150032, -111.892622), 'VT': (44.045876, -72.710686),
    'VA': (37.769337, -78.169968), 'WA': (47.400902, -121.490494), 'WV': (38.491226, -80.954453),
    'WI': (44.268543, -89.616508), 'WY': (42.755966, -107.302490), 'DC': (38.907192, -77.036873)
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_openai_client() -> OpenAI:
    """Initialize OpenAI client using Streamlit secrets."""
    try:
        # Try Streamlit secrets first (for cloud deployment)
        api_key = st.secrets.get("openai", {}).get("api_key") or st.secrets.get("OPENAI_API_KEY")
    except (AttributeError, FileNotFoundError, KeyError):
        # Fallback to local secrets file for development
        SECRETS_FILE = 'openai_secrets.json'
        if os.path.exists(SECRETS_FILE):
            try:
                with open(SECRETS_FILE, 'r') as f:
                    secrets = json.load(f)
                    api_key = secrets.get('openai_api_key')
            except Exception as e:
                st.error(f"Error reading secrets file: {e}")
                st.stop()
        else:
            st.error("OpenAI API key not found. Please configure Streamlit secrets or create openai_secrets.json")
            st.stop()
    
    if not api_key:
        st.error("OpenAI API key not found. Please configure Streamlit secrets.")
        st.stop()
    
    return OpenAI(api_key=api_key)

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates in miles using Haversine formula."""
    from math import radians, sin, cos, sqrt, atan2
    R = 3959  # Earth radius in miles
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def scrape_website_content(force_refresh: bool = False) -> List[Dict]:
    """Scrape content from ridewithvia.com and cache it.
    
    Args:
        force_refresh: If True, ignore cache and re-scrape everything
    """
    # Always use cache if it exists (unless force_refresh)
    if not force_refresh and os.path.exists(CONTENT_CACHE_FILE):
        try:
            with open(CONTENT_CACHE_FILE, 'r') as f:
                cached = json.load(f)
                if cached:  # Only use cache if it has content
                    # Check if embeddings exist (they might not if cache was created before embedding feature)
                    articles_with_embeddings = sum(1 for a in cached if a.get('embedding'))
                    if articles_with_embeddings < len(cached):
                        st.info(f"✅ Using cached content ({len(cached)} articles). {articles_with_embeddings}/{len(cached)} have embeddings. Embeddings will be generated on-demand.")
                    else:
                        st.success(f"✅ Using cached content ({len(cached)} articles) with embeddings. Ready for semantic search!")
                    return cached
        except Exception as e:
            st.warning(f"Error loading cache: {e}. Re-scraping...")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    status_text.info("Building comprehensive content cache... This may take a few minutes.")
    articles = []
    seen_urls = set()
    urls_to_visit = []
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        # Start with main pages - crawl from these
        seed_urls = [
            '/',
            '/audience/',
            '/solutions/',
            '/solutions/microtransit/',
            '/solutions/paratransit/',
            '/solutions/on-demand-transit/',
            '/resources/',
            '/blog/',
            '/case-studies/',
            '/about/',
        ]
        
        # Phase 1: Discover all URLs
        status_text.info("Phase 1: Discovering all pages on the website...")
        for seed in seed_urls:
            url = urljoin(WEBSITE_URL, seed)
            urls_to_visit.append(url)
        
        visited_count = 0
        max_pages = 200  # Limit to prevent infinite loops
        
        while urls_to_visit and visited_count < max_pages:
            current_url = urls_to_visit.pop(0)
            if current_url in seen_urls:
                continue
            
            seen_urls.add(current_url)
            visited_count += 1
            
            if visited_count % 10 == 0:
                progress_bar.progress(min(0.5, visited_count / max_pages))
                status_text.info(f"Discovering pages... Found {len(seen_urls)} unique URLs")
            
            try:
                response = requests.get(current_url, timeout=10, headers=headers, allow_redirects=True)
                response.raise_for_status()
                
                # Only process HTML pages
                if 'text/html' not in response.headers.get('content-type', ''):
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract all links on this page
                for link in soup.find_all('a', href=True):
                    href = link.get('href')
                    if not href:
                        continue
                    
                    # Normalize URL
                    if href.startswith('/'):
                        full_url = urljoin(WEBSITE_URL, href)
                    elif href.startswith('http') and 'ridewithvia.com' in href:
                        full_url = href
                    else:
                        continue
                    
                    # Only include ridewithvia.com pages
                    if 'ridewithvia.com' in full_url and full_url not in seen_urls:
                        # Filter to relevant content pages - include audience, solutions, resources directories
                        if any(path in full_url for path in ['/blog/', '/resources/', '/solutions/', '/audience/', '/case-studies/', '/about/']):
                            urls_to_visit.append(full_url)
                            seen_urls.add(full_url)
                            
                            # Extract title
                            title = link.get_text(strip=True) or link.get('title', '') or link.get('aria-label', '')
                            if not title or len(title) < 5:
                                # Try to get title from page
                                title_elem = soup.find('title')
                                title = title_elem.get_text(strip=True) if title_elem else full_url.split('/')[-1]
                            
                            if title and len(title) > 5 and len(title) < 300:
                                # Determine article type based on URL path
                                if '/blog/' in full_url:
                                    article_type = 'blog'
                                elif '/resources/' in full_url:
                                    article_type = 'resource'
                                elif '/case-studies/' in full_url:
                                    article_type = 'case-study'
                                elif '/solutions/' in full_url:
                                    article_type = 'solution'
                                elif '/audience/' in full_url:
                                    article_type = 'audience'
                                else:
                                    article_type = 'page'
                                
                                articles.append({
                                    'url': full_url,
                                    'title': title,
                                    'content': '',
                                    'description': '',
                                    'type': article_type,
                                    'thumbnail': ''  # Will be filled during content scraping
                                })
            except Exception as e:
                continue
        
        # Phase 2: Scrape content from all discovered pages
        total_articles = len(articles)
        status_text.info(f"Phase 2: Scraping content from {total_articles} pages...")
        
        for idx, article in enumerate(articles):
            progress_bar.progress(0.5 + (idx + 1) / total_articles * 0.5)
            
            if (idx + 1) % 10 == 0:
                status_text.info(f"Scraping content... {idx + 1}/{total_articles} pages")
            
            try:
                response = requests.get(article['url'], timeout=10, headers=headers, allow_redirects=True)
                response.raise_for_status()
                
                if 'text/html' not in response.headers.get('content-type', ''):
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Get page title if not already set
                if not article['title'] or article['title'] == article['url'].split('/')[-1]:
                    title_elem = soup.find('title')
                    if title_elem:
                        article['title'] = title_elem.get_text(strip=True)
                
                # Extract main content
                main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content') or soup.find('body')
                if main_content:
                    # Remove script and style elements
                    for script in main_content(["script", "style", "nav", "header", "footer", "aside"]):
                        script.decompose()
                    content_text = main_content.get_text(strip=True, separator=' ')
                    article['content'] = content_text[:5000]  # Increased limit for comprehensive cache
                
                # Extract meta description
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                if meta_desc:
                    article['description'] = meta_desc.get('content', '')
                else:
                    og_desc = soup.find('meta', attrs={'property': 'og:description'})
                    if og_desc:
                        article['description'] = og_desc.get('content', '')
                
                # Extract thumbnail/image
                # Try og:image first (most reliable)
                og_image = soup.find('meta', attrs={'property': 'og:image'})
                if og_image and og_image.get('content'):
                    image_url = og_image.get('content')
                    # Make absolute URL if relative
                    if image_url.startswith('/'):
                        image_url = urljoin(WEBSITE_URL, image_url)
                    article['thumbnail'] = image_url
                else:
                    # Try twitter:image
                    twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
                    if twitter_image and twitter_image.get('content'):
                        image_url = twitter_image.get('content')
                        if image_url.startswith('/'):
                            image_url = urljoin(WEBSITE_URL, image_url)
                        article['thumbnail'] = image_url
                    else:
                        # Try to find first large image in content
                        img_tags = soup.find_all('img', src=True)
                        for img in img_tags:
                            src = img.get('src', '')
                            if src and not any(skip in src.lower() for skip in ['icon', 'logo', 'avatar', 'button']):
                                if src.startswith('/'):
                                    src = urljoin(WEBSITE_URL, src)
                                elif not src.startswith('http'):
                                    src = urljoin(article['url'], src)
                                # Check if it's a reasonable size (not tiny icons)
                                width = img.get('width', '')
                                height = img.get('height', '')
                                if (width and int(width) > 200) or (height and int(height) > 200) or not (width or height):
                                    article['thumbnail'] = src
                                    break
                
                # Extract location/state mentions
                # First, try to extract from structured "Location" field on case study pages
                mentioned_states = []
                
                # Look for "Location" label/heading in the HTML (case studies have this)
                # Try multiple patterns to find the location field
                location_text = None
                
                # Pattern 1: Look for elements with "Location" text followed by location info
                location_heading = soup.find(string=re.compile(r'Location', re.I))
                if location_heading:
                    # Find the next sibling or parent that contains the actual location
                    parent = location_heading.find_parent()
                    if parent:
                        # Get all text from the parent container
                        container_text = parent.get_text(separator=' ', strip=True)
                        # Look for "City, State" pattern after "Location"
                        location_match = re.search(r'Location[:\s]+([^,\n]+),\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', container_text, re.IGNORECASE)
                        if location_match:
                            location_text = location_match.group(2).strip()
                        # Also try simpler pattern: just find state after comma
                        if not location_text:
                            location_match = re.search(r'Location[:\s]+[^,]+,\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', container_text, re.IGNORECASE)
                            if location_match:
                                location_text = location_match.group(1).strip()
                
                # Pattern 2: Look for case_study_location class or similar
                location_div = soup.find(class_=re.compile(r'location', re.I))
                if location_div and not location_text:
                    location_text = location_div.get_text(strip=True)
                    # Extract state from "City, State" format
                    location_match = re.search(r',\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', location_text)
                    if location_match:
                        location_text = location_match.group(1).strip()
                
                # Pattern 3: Search entire page content for "Location: City, State" pattern
                if not location_text:
                    page_text = soup.get_text(separator=' ', strip=True)
                    location_match = re.search(r'Location[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', page_text, re.IGNORECASE)
                    if location_match:
                        location_text = location_match.group(2).strip()
                
                # Map state name to abbreviation if found
                if location_text:
                    full_state_names = {
                        'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA',
                        'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE', 'florida': 'FL', 'georgia': 'GA',
                        'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA',
                        'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
                        'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS', 'missouri': 'MO',
                        'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ',
                        'new mexico': 'NM', 'new york': 'NY', 'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH',
                        'oklahoma': 'OK', 'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
                        'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT', 'vermont': 'VT',
                        'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY',
                        'district of columbia': 'DC', 'washington dc': 'DC', 'dc': 'DC'
                    }
                    state_lower = location_text.lower()
                    if state_lower in full_state_names:
                        mentioned_states.append(full_state_names[state_lower])
                
                # If no structured location found, search content but with stricter matching
                if not mentioned_states:
                    content_lower = article.get('content', '').lower()
                    content_full = article.get('content', '')
                    
                    # Use regex with word boundaries for state abbreviations to avoid false matches
                    import re
                    for state_abbr in STATE_COORDINATES.keys():
                        # Match state abbreviation with word boundaries (not inside other words)
                        # Pattern: word boundary, state code, word boundary or punctuation
                        pattern = r'\b' + re.escape(state_abbr) + r'\b'
                        if re.search(pattern, content_full, re.IGNORECASE):
                            mentioned_states.append(state_abbr)
                    
                    # Check for full state names with word boundaries
                    full_state_names = {
                        'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA',
                        'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE', 'florida': 'FL', 'georgia': 'GA',
                        'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA',
                        'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
                        'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS', 'missouri': 'MO',
                        'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ',
                        'new mexico': 'NM', 'new york': 'NY', 'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH',
                        'oklahoma': 'OK', 'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
                        'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT', 'vermont': 'VT',
                        'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY',
                        'district of columbia': 'DC', 'washington dc': 'DC', 'dc': 'DC'
                    }
                    
                    for state_name, state_abbr in full_state_names.items():
                        # Use word boundaries to avoid matching "california" inside "californian" etc.
                        pattern = r'\b' + re.escape(state_name) + r'\b'
                        if re.search(pattern, content_lower) and state_abbr not in mentioned_states:
                            mentioned_states.append(state_abbr)
                
                if mentioned_states:
                    article['states'] = list(set(mentioned_states))  # Remove duplicates
                
            except Exception as e:
                continue
        
        progress_bar.empty()
        status_text.success(f"✅ Content cache built! Found {len(articles)} pages.")
        
        # Cache the results (embeddings will be generated on-demand)
        with open(CONTENT_CACHE_FILE, 'w') as f:
            json.dump(articles, f, indent=2)
        
        st.success(f"✅ Content cached to {CONTENT_CACHE_FILE}. This cache will be used for all future sessions - no more scraping needed!")
        st.info("💡 Embeddings will be generated automatically when you ask questions for better semantic search.")
        
        return articles
    except Exception as e:
        st.error(f"Error scraping website: {e}")
        return []

def get_articles_by_location(articles: List[Dict], user_state: str, max_distance: int = 500) -> List[Dict]:
    """Filter articles based on location (within max_distance miles)."""
    if user_state not in STATE_COORDINATES:
        return articles
    
    user_lat, user_lon = STATE_COORDINATES[user_state]
    filtered = []
    articles_with_states = []
    articles_without_states = []
    
    for article in articles:
        # Check if article mentions states
        if 'states' in article and article.get('states'):
            articles_with_states.append(article)
        else:
            articles_without_states.append(article)
    
    # First, prioritize articles with state info that matches location
    for article in articles_with_states:
        for state in article['states']:
            if state in STATE_COORDINATES:
                state_lat, state_lon = STATE_COORDINATES[state]
                distance = calculate_distance(user_lat, user_lon, state_lat, state_lon)
                if distance <= max_distance:
                    filtered.append(article)
                    break
    
    # If we have enough location-matched articles, return them
    if len(filtered) >= 4:
        return filtered
    elif len(filtered) > 0:
        # Add some articles without state info to reach at least 4
        remaining_needed = 4 - len(filtered)
        filtered.extend(articles_without_states[:remaining_needed])
        return filtered
    else:
        # No location matches - return all articles without state info
        # This allows variety instead of always the same ones
        # Shuffle or return all to avoid always getting the same first ones
        import random
        shuffled = articles_without_states.copy()
        random.shuffle(shuffled)
        return shuffled[:10] if shuffled else []

def recommend_articles(articles: List[Dict], user_type: str, user_state: str, client: OpenAI) -> Dict:
    """Recommend articles: 3 general + 2 geographically relevant case studies.
    
    Returns:
        Dict with 'general' (list of 3) and 'case_studies' (list of 2 or message)
    """
    if not articles:
        return {'general': [], 'case_studies': []}
    
    # Filter articles by type
    if user_type == 'city':
        relevant_articles = [a for a in articles if any(keyword in a.get('content', '').lower() or 
                            keyword in a.get('title', '').lower() or
                            keyword in a.get('description', '').lower()
                            for keyword in ['microtransit', 'paratransit', 'city', 'municipal', 'urban'])]
    elif user_type == 'transit_agency':
        relevant_articles = [a for a in articles if any(keyword in a.get('content', '').lower() or
                            keyword in a.get('title', '').lower() or
                            keyword in a.get('description', '').lower()
                            for keyword in ['paratransit', 'transit', 'agency', 'public transportation'])]
    else:
        relevant_articles = articles
    
    # Separate case studies from general content
    # Case studies can be identified by: type, title, URL pattern, or content
    case_studies = [a for a in relevant_articles if 
                    'case-study' in a.get('type', '').lower() or 
                    'case study' in a.get('title', '').lower() or
                    'case study' in a.get('content', '').lower()[:500] or
                    '/case-studies/' in a.get('url', '').lower() or
                    '-case-study' in a.get('url', '').lower() or
                    'case-study' in a.get('url', '').lower() or
                    ('success story' in a.get('title', '').lower() or 'success story' in a.get('content', '').lower()[:500])]
    
    general_articles = [a for a in relevant_articles if a not in case_studies]
    
    # Get 3 general articles
    if len(general_articles) <= 3:
        selected_general = general_articles
    else:
        # Use LLM to select top 3 general articles
        articles_summary = "\n".join([f"{i+1}. {a['title']} - {a.get('description', a.get('content', '')[:200])}" 
                                      for i, a in enumerate(general_articles[:30])])
        user_type_display = "city" if user_type == 'city' else "transit agency"
        prompt = f"""Select the top 3 most relevant articles for a {user_type_display} in {user_state}:

{articles_summary}

Return only the numbers (1-30) of the top 3 articles, separated by commas."""
        
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Return only numbers separated by commas, no other text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=30
            )
            import re
            numbers = re.findall(r'\d+', response.choices[0].message.content.strip())
            selected_indices = [int(x) - 1 for x in numbers[:3] if x.isdigit() and 0 <= int(x) - 1 < len(general_articles)]
            selected_general = [general_articles[i] for i in selected_indices[:3]] if selected_indices else general_articles[:3]
        except:
            selected_general = general_articles[:3]
    
    # Get 4 geographically relevant case studies
    if case_studies:
        # Filter case studies by location
        location_case_studies = get_articles_by_location(case_studies, user_state, max_distance=500)
        
        if location_case_studies:
            # Use LLM to select top 4 geographically relevant case studies
            if len(location_case_studies) <= 4:
                selected_case_studies = location_case_studies
            else:
                articles_summary = "\n".join([f"{i+1}. {a['title']} - Location: {a.get('states', ['Unknown'])[0] if a.get('states') else 'Unknown'} - {a.get('description', a.get('content', '')[:200])}" 
                                              for i, a in enumerate(location_case_studies[:30])])
                prompt = f"""Select the top 4 most relevant case studies for {user_state}. Prioritize case studies from {user_state} or nearby states:

{articles_summary}

Return only the numbers (1-30) of the top 4 articles, separated by commas."""
                try:
                    response = client.chat.completions.create(
                        model="gpt-4",
                        messages=[
                            {"role": "system", "content": "Return only numbers separated by commas, no other text."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.3,
                        max_tokens=30
                    )
                    import re
                    numbers = re.findall(r'\d+', response.choices[0].message.content.strip())
                    selected_indices = [int(x) - 1 for x in numbers[:4] if x.isdigit() and 0 <= int(x) - 1 < len(location_case_studies)]
                    selected_case_studies = [location_case_studies[i] for i in selected_indices[:4]] if selected_indices else location_case_studies[:4]
                except:
                    selected_case_studies = location_case_studies[:4]
        else:
            selected_case_studies = None  # No geographically relevant case studies
    else:
        selected_case_studies = None
    
    return {
        'general': selected_general,
        'case_studies': selected_case_studies
    }

def get_article_embedding(article: Dict, client: OpenAI, save_to_cache: bool = True) -> Optional[List[float]]:
    """Generate embedding for an article. Returns embedding and optionally saves to cache."""
    if 'embedding' in article and article['embedding']:
        return article['embedding']
    
    # Create text for embedding: title + description + first part of content
    text_parts = []
    if article.get('title'):
        text_parts.append(article['title'])
    if article.get('description'):
        text_parts.append(article['description'])
    if article.get('content'):
        # Use first 500 chars of content for embedding
        text_parts.append(article['content'][:500])
    
    text = ' '.join(text_parts)
    if not text.strip():
        return None
    
    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        embedding = response.data[0].embedding
        
        # Save embedding to article dict (will be saved to cache later)
        if save_to_cache:
            article['embedding'] = embedding
        
        return embedding
    except Exception as e:
        st.warning(f"Error generating embedding: {e}")
        return None

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def find_similar_articles(query: str, articles: List[Dict], client: OpenAI, top_k: int = 25) -> List[Dict]:
    """Find most similar articles to query using semantic search."""
    # Generate embedding for query
    try:
        query_response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=query
        )
        query_embedding = query_response.data[0].embedding
    except Exception as e:
        st.warning(f"Error generating query embedding: {e}")
        # Fallback to keyword matching
        return articles[:top_k]
    
    # Get or generate embeddings for articles
    article_scores = []
    embeddings_generated = 0
    for article in articles:
        embedding = get_article_embedding(article, client, save_to_cache=True)
        if embedding:
            similarity = cosine_similarity(query_embedding, embedding)
            article_scores.append((similarity, article))
            if 'embedding' not in article or not article.get('embedding'):
                embeddings_generated += 1
        else:
            # If embedding fails, give it a low score
            article_scores.append((0.0, article))
    
    # Save updated articles with embeddings to cache
    if embeddings_generated > 0:
        try:
            with open(CONTENT_CACHE_FILE, 'w') as f:
                json.dump(articles, f, indent=2)
        except Exception as e:
            pass  # Silently fail - not critical
    
    # Sort by similarity score (highest first)
    article_scores.sort(key=lambda x: x[0], reverse=True)
    
    # Return top K articles
    return [article for _, article in article_scores[:top_k]]

def get_google_sheets_config_status() -> Dict:
    """
    Return a status dict for diagnostics (no secrets exposed).
    Keys: 'configured' (bool), 'reason' (str), 'hint' (str).
    """
    if not GSPREAD_AVAILABLE:
        return {
            'configured': False,
            'reason': 'gspread not installed',
            'hint': 'Add gspread and google-auth to requirements.txt and redeploy.',
        }
    try:
        secrets = getattr(st, 'secrets', None)
        if not secrets:
            return {
                'configured': False,
                'reason': 'No secrets available',
                'hint': 'In Streamlit Cloud use App → Settings → Secrets. Locally use .streamlit/secrets.toml with a [google_sheets] section.',
            }
        if 'google_sheets' not in secrets:
            return {
                'configured': False,
                'reason': 'No [google_sheets] section in secrets',
                'hint': 'In Streamlit Cloud: App → Settings → Secrets. Add a [google_sheets] section with spreadsheet_id and service_account_json.',
            }
        gs = secrets.get('google_sheets', {})
        if not gs.get('service_account_json'):
            return {
                'configured': False,
                'reason': 'service_account_json missing in [google_sheets]',
                'hint': 'Paste your full service account JSON (from Google Cloud Console) as service_account_json. In the JSON, keep private_key on one line with \\n for newlines.',
            }
        # Try to actually connect (without exposing secrets)
        client = get_google_sheets_client()
        if client is None:
            return {
                'configured': False,
                'reason': 'Credentials present but connection failed',
                'hint': 'Check: (1) JSON is valid and private_key uses \\n for newlines, (2) Sheet is shared with the service account email (Editor), (3) Google Sheets & Drive APIs are enabled.',
            }
        return {'configured': True, 'reason': 'OK', 'hint': ''}
    except Exception as e:
        return {
            'configured': False,
            'reason': f'Error checking config: {type(e).__name__}',
            'hint': 'Add [google_sheets] with spreadsheet_id and service_account_json to Streamlit Secrets.',
        }


def get_google_sheets_client():
    """Initialize Google Sheets client using Streamlit secrets."""
    if not GSPREAD_AVAILABLE:
        return None
    
    try:
        # Try to get credentials from Streamlit secrets
        try:
            # Option 1: Service account JSON as string in secrets
            if 'google_sheets' in st.secrets and 'service_account_json' in st.secrets['google_sheets']:
                creds_json = st.secrets['google_sheets']['service_account_json']
                if isinstance(creds_json, str):
                    # Try to parse as JSON string
                    try:
                        creds_dict = json.loads(creds_json)
                    except json.JSONDecodeError:
                        # If it's already a dict (Streamlit might parse it), use it directly
                        creds_dict = creds_json if isinstance(creds_json, dict) else json.loads(creds_json.replace('\\n', '\n'))
                else:
                    creds_dict = creds_json
                # Ensure private_key has real newlines if stored as \n
                if isinstance(creds_dict.get('private_key'), str) and '\\n' in creds_dict['private_key']:
                    creds_dict = dict(creds_dict)
                    creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')
                creds = Credentials.from_service_account_info(creds_dict, scopes=[
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ])
                return gspread.authorize(creds)
        except (AttributeError, KeyError, FileNotFoundError, json.JSONDecodeError) as e:
            # Store error for debugging
            if 'logging_errors' not in st.session_state:
                st.session_state.logging_errors = []
            st.session_state.logging_errors.append(f"Error loading credentials from secrets: {str(e)}")
            pass
        
        # Option 2: Service account file path (for local development)
        try:
            if 'google_sheets' in st.secrets and 'credentials_path' in st.secrets['google_sheets']:
                creds_path = st.secrets['google_sheets']['credentials_path']
                creds = Credentials.from_service_account_file(creds_path, scopes=[
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ])
                return gspread.authorize(creds)
        except (AttributeError, KeyError, FileNotFoundError):
            pass
        
        # Option 3: Try default local credentials file paths (for local development)
        # Try multiple possible paths relative to current working directory
        script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
        default_creds_paths = [
            'google_sheets_credentials.json',
            os.path.join(script_dir, 'google_sheets_credentials.json'),
            '../GitLab/rgrowth-all/Product_Education_Machine/Product Education Machine.json',
            '../../GitLab/rgrowth-all/Product_Education_Machine/Product Education Machine.json',
            os.path.join(script_dir, '../GitLab/rgrowth-all/Product_Education_Machine/Product Education Machine.json'),
            os.path.join(script_dir, '../../GitLab/rgrowth-all/Product_Education_Machine/Product Education Machine.json'),
        ]
        
        for creds_path in default_creds_paths:
            full_path = os.path.abspath(creds_path) if not os.path.isabs(creds_path) else creds_path
            if os.path.exists(full_path):
                try:
                    creds = Credentials.from_service_account_file(full_path, scopes=[
                        'https://www.googleapis.com/auth/spreadsheets',
                        'https://www.googleapis.com/auth/drive'
                    ])
                    return gspread.authorize(creds)
                except Exception:
                    continue
        
        return None
    except Exception as e:
        return None


def _get_worksheet(spreadsheet, sheet_name: str):
    """Get worksheet by name, or first sheet if name not found (for your 'question'/'answer' tab)."""
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        pass
    try:
        return spreadsheet.get_worksheet(0)
    except Exception:
        return None


def log_qa_pair(question: str, answer: str) -> bool:
    """Log question and answer to Google Sheets (primary), CSV file (fallback), and session state.
    Returns True if logged to Google Sheets, False otherwise."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    log_entry = {
        'timestamp': timestamp,
        'question': question,
        'answer': answer
    }
    
    # Store in session state (persists during session)
    if 'qa_logs' not in st.session_state:
        st.session_state.qa_logs = []
    st.session_state.qa_logs.append(log_entry)
    
    # Try to log to Google Sheets first (permanent storage)
    google_sheets_success = False
    if GSPREAD_AVAILABLE:
        try:
            client = get_google_sheets_client()
            if client:
                # Get spreadsheet ID from secrets or use default
                spreadsheet_id = None
                sheet_name = GOOGLE_SHEETS_SHEET_NAME
                
                try:
                    if 'google_sheets' in st.secrets:
                        spreadsheet_id = st.secrets['google_sheets'].get('spreadsheet_id', GOOGLE_SHEETS_SPREADSHEET_ID)
                        sheet_name = st.secrets['google_sheets'].get('sheet_name', GOOGLE_SHEETS_SHEET_NAME)
                    else:
                        spreadsheet_id = GOOGLE_SHEETS_SPREADSHEET_ID
                except (AttributeError, KeyError):
                    spreadsheet_id = GOOGLE_SHEETS_SPREADSHEET_ID
                
                if spreadsheet_id:
                    spreadsheet = client.open_by_key(spreadsheet_id)
                    worksheet = _get_worksheet(spreadsheet, sheet_name)
                    if worksheet is None:
                        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=2)
                        worksheet.append_row(['question', 'answer'])
                    # Match your sheet: two columns "question", "answer"
                    worksheet.append_row([question, answer])
                    google_sheets_success = True
                    logging.info("Successfully logged Q&A pair to Google Sheets")
        except Exception as e:
            logging.warning(f"Error logging to Google Sheets: {e}")
            # Continue to CSV fallback
    
    # Fallback to CSV file if Google Sheets failed or not configured
    if not google_sheets_success:
        try:
            file_exists = os.path.exists(QA_LOG_FILE)
            df_new = pd.DataFrame([log_entry])
            if file_exists:
                df_new.to_csv(QA_LOG_FILE, mode='a', header=False, index=False, encoding='utf-8')
            else:
                df_new.to_csv(QA_LOG_FILE, mode='w', header=True, index=False, encoding='utf-8')
            
            logging.info(f"Successfully logged Q&A pair to {QA_LOG_FILE}")
        except Exception as e:
            logging.error(f"Error logging Q&A pair to file: {e}")
            import sys
            print(f"ERROR: Failed to log Q&A pair to file: {e}", file=sys.stderr)
    
    return google_sheets_success

def query_website_content(query: str, articles: List[Dict], client: OpenAI) -> Dict:
    """Use LLM to answer questions about website content using semantic search.
    
    Returns:
        Dict with 'answer' (str) and 'sources' (List[Dict]) - list of article dicts used as sources
    """
    # Use semantic search to find most relevant articles
    with st.spinner("Finding relevant articles..."):
        similar_articles = find_similar_articles(query, articles, client, top_k=25)
    
    # Prioritize case studies if query mentions them (but still use semantic results)
    query_lower = query.lower()
    if 'case study' in query_lower or 'case studies' in query_lower or 'success story' in query_lower:
        # Boost case studies in the results
        case_studies = [a for a in similar_articles if 'case-study' in a.get('type', '').lower() or 
                        'case study' in a.get('title', '').lower() or
                        '/case-studies/' in a.get('url', '').lower()]
        other_articles = [a for a in similar_articles if a not in case_studies]
        prioritized = case_studies + other_articles
    else:
        prioritized = similar_articles
    
    # Use top 20 most relevant articles
    context_articles = prioritized[:20]
    context = "\n\n".join([f"Title: {a['title']}\nURL: {a.get('url', '')}\nContent: {a.get('content', a.get('description', ''))[:500]}" 
                           for a in context_articles])  # Increased to 500 chars since we have better relevance
    
    prompt = f"""You are a helpful assistant that answers questions about ridewithvia.com based on the following content:

{context}

Question: {query}

Answer based only on the content provided above. Include specific URLs when mentioning articles or case studies. If the answer is not in the content, say so."""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant for ridewithvia.com. Answer questions based only on the provided content. Include URLs when mentioning specific articles."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=600
        )
        answer = response.choices[0].message.content
        
        # Log the Q&A pair
        logged_to_sheets = log_qa_pair(query, answer)
        
        # Return top 5 most relevant articles as sources (these are the ones most likely used)
        sources = context_articles[:5]
        
        return {
            'answer': answer,
            'sources': sources,
            'logged_to_sheets': logged_to_sheets
        }
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        # Log errors too
        logged_to_sheets = log_qa_pair(query, error_msg)
        return {
            'answer': error_msg,
            'sources': [],
            'logged_to_sheets': logged_to_sheets
        }

# ============================================================================
# STREAMLIT APP
# ============================================================================

def main():
    st.set_page_config(
        page_title="Via - Personalized Content",
        page_icon="🚌",
        layout="wide"
    )
    
    # Initialize session state
    if 'user_profile' not in st.session_state:
        st.session_state.user_profile = None
    if 'articles' not in st.session_state:
        st.session_state.articles = []
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    if 'show_logs' not in st.session_state:
        st.session_state.show_logs = False
    if 'qa_logs' not in st.session_state:
        st.session_state.qa_logs = []
        # Try to load existing logs from Google Sheets first, then CSV file
        loaded_from_sheets = False
        
        # Try Google Sheets first
        if GSPREAD_AVAILABLE:
            try:
                client = get_google_sheets_client()
                if client:
                    spreadsheet_id = None
                    sheet_name = GOOGLE_SHEETS_SHEET_NAME
                    
                    try:
                        if 'google_sheets' in st.secrets:
                            spreadsheet_id = st.secrets['google_sheets'].get('spreadsheet_id', GOOGLE_SHEETS_SPREADSHEET_ID)
                            sheet_name = st.secrets['google_sheets'].get('sheet_name', GOOGLE_SHEETS_SHEET_NAME)
                        else:
                            spreadsheet_id = GOOGLE_SHEETS_SPREADSHEET_ID
                    except (AttributeError, KeyError):
                        spreadsheet_id = GOOGLE_SHEETS_SPREADSHEET_ID
                    
                    if spreadsheet_id:
                        spreadsheet = client.open_by_key(spreadsheet_id)
                        worksheet = _get_worksheet(spreadsheet, sheet_name)
                        if worksheet:
                            records = worksheet.get_all_records()
                            if records:
                                st.session_state.qa_logs = records
                                loaded_from_sheets = True
                                logging.info(f"Loaded {len(records)} Q&A pairs from Google Sheets")
            except Exception as e:
                logging.warning(f"Could not load logs from Google Sheets: {e}")
        
        # Fallback to CSV file if Google Sheets didn't work
        if not loaded_from_sheets and os.path.exists(QA_LOG_FILE):
            try:
                df_existing = pd.read_csv(QA_LOG_FILE)
                st.session_state.qa_logs = df_existing.to_dict('records')
                logging.info(f"Loaded {len(st.session_state.qa_logs)} Q&A pairs from CSV file")
            except Exception as e:
                logging.warning(f"Could not load existing logs from CSV: {e}")
    
    # Profile Collection Page
    if st.session_state.user_profile is None:
        st.title("Welcome to Via")
        st.markdown("### Tell us about yourself to get personalized content")
        
        with st.form("user_profile_form"):
            st.markdown("**Are you a city or transit agency?** (Select one)")
            is_city = st.radio(
                "Organization Type",
                ["City", "Transit Agency"],
                index=None
            )
            
            state = st.selectbox(
                "What state are you in?",
                [''] + sorted(STATE_COORDINATES.keys())
            )
            
            submitted = st.form_submit_button("Continue")
            
            if submitted:
                if is_city is None:
                    st.error("Please select whether you are a city or transit agency")
                elif not state:
                    st.error("Please select your state")
                else:
                    user_type = 'city' if is_city == "City" else 'transit_agency'
                    st.session_state.user_profile = {
                        'type': user_type,
                        'state': state,
                        'is_city': is_city == "City",
                        'is_transit_agency': is_city == "Transit Agency"
                    }
                    st.rerun()
    
    # Home Page
    else:
        user_profile = st.session_state.user_profile
        
        # Load articles (always use cache if available)
        if not st.session_state.articles:
            try:
                st.session_state.articles = scrape_website_content(force_refresh=False)
            except Exception as e:
                st.error(f"Error loading articles: {e}")
                st.session_state.articles = []
        
        # Initialize OpenAI client
        try:
            client = get_openai_client()
        except Exception as e:
            st.error(f"Error initializing OpenAI client: {e}")
            st.stop()
        
        # Header
        col1, col2, col3, col4, col5 = st.columns([2.5, 1, 1, 1, 0.8])
        with col1:
            st.title("Via Content Hub")
        with col2:
            if st.button("Change Profile"):
                st.session_state.user_profile = None
                st.session_state.chat_history = []
                st.rerun()
        with col3:
            if st.button("🔄 Refresh Cache"):
                if os.path.exists(CONTENT_CACHE_FILE):
                    os.remove(CONTENT_CACHE_FILE)
                st.session_state.articles = []
                st.rerun()
        with col4:
            log_count = len(st.session_state.get('qa_logs', []))
            button_label = f"📊 Logs ({log_count})" if log_count > 0 else "📊 View Logs"
            if st.button(button_label):
                st.session_state.show_logs = not st.session_state.get('show_logs', False)
                st.rerun()
        with col5:
            # Always show log count badge
            log_count = len(st.session_state.get('qa_logs', []))
            if log_count > 0:
                st.metric("Q&A Logged", log_count, label_visibility="collapsed")
        
        # Show user profile info
        user_type_display = "City" if user_profile['is_city'] else "Transit Agency"
        st.info(f"👤 Profile: {user_type_display} in {user_profile['state']}")
        
        # Show Google Sheets setup status if not configured
        try:
            status = get_google_sheets_config_status()
            if not status['configured']:
                st.warning(
                    "⚠️ **Google Sheets not configured** — Logs will only be saved to CSV (may not persist in Streamlit Cloud)."
                )
                with st.expander("What to add in Streamlit Secrets", expanded=True):
                    st.markdown(f"**Reason:** {status['reason']}")
                    st.markdown(f"**Fix:** {status['hint']}")
                    st.markdown("See **GOOGLE_SHEETS_SETUP.md** for step-by-step setup (create sheet, service account, share sheet, then add to Secrets).")
        except Exception:
            pass
        
        # Show logs if requested
        if st.session_state.show_logs:
            st.markdown("---")
            st.header("📊 Q&A Log")
            
            # Get logs from session state (primary source)
            qa_logs = st.session_state.get('qa_logs', [])
            
            if qa_logs:
                # Convert to DataFrame for display
                df_logs = pd.DataFrame(qa_logs)
                
                # Show stats
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Q&A Pairs", len(df_logs))
                with col2:
                    if 'timestamp' in df_logs.columns:
                        latest = df_logs['timestamp'].max() if len(df_logs) > 0 else "N/A"
                        st.metric("Latest Entry", latest[:10] if latest != "N/A" else "N/A")
                with col3:
                    # Check storage status
                    storage_status = "⚠️ Unknown"
                    storage_source = "Unknown"
                    if GSPREAD_AVAILABLE:
                        try:
                            client = get_google_sheets_client()
                            if client:
                                storage_status = "✅ Google Sheets"
                                storage_source = "Google Sheets"
                            else:
                                storage_status = "⚠️ CSV Only"
                                storage_source = "CSV"
                        except:
                            storage_status = "⚠️ CSV Only"
                            storage_source = "CSV"
                    else:
                        storage_status = "⚠️ CSV Only"
                        storage_source = "CSV"
                    st.metric("Storage", storage_status)
                with col4:
                    # Show link to Google Sheet if available
                    if storage_source == "Google Sheets":
                        try:
                            spreadsheet_id = None
                            try:
                                if 'google_sheets' in st.secrets:
                                    spreadsheet_id = st.secrets['google_sheets'].get('spreadsheet_id', GOOGLE_SHEETS_SPREADSHEET_ID)
                                else:
                                    spreadsheet_id = GOOGLE_SHEETS_SPREADSHEET_ID
                            except (AttributeError, KeyError):
                                spreadsheet_id = GOOGLE_SHEETS_SPREADSHEET_ID
                            
                            if spreadsheet_id:
                                sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
                                st.markdown(f"[📊 View in Sheets]({sheet_url})")
                        except:
                            pass
                
                st.markdown("")
                
                # Display logs
                st.dataframe(df_logs, width='stretch', hide_index=True, use_container_width=True)
                
                st.markdown("")
                
                # Download buttons
                col1, col2 = st.columns(2)
                with col1:
                    # Download from session state (most up-to-date)
                    csv = df_logs.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Current Logs (CSV)",
                        data=csv,
                        file_name=f"qa_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        help="Download all logs from current session"
                    )
                with col2:
                    # Try to download from file if it exists
                    if os.path.exists(QA_LOG_FILE):
                        try:
                            with open(QA_LOG_FILE, 'rb') as f:
                                file_data = f.read()
                            st.download_button(
                                label="📥 Download File Logs (CSV)",
                                data=file_data,
                                file_name=f"qa_log_file_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv",
                                help="Download logs from saved file"
                            )
                        except Exception as e:
                            st.caption(f"File read error: {e}")
                    else:
                        st.caption("File not yet created")
                
                # Storage info
                st.markdown("---")
                if storage_source == "Google Sheets":
                    try:
                        spreadsheet_id = None
                        try:
                            if 'google_sheets' in st.secrets:
                                spreadsheet_id = st.secrets['google_sheets'].get('spreadsheet_id', GOOGLE_SHEETS_SPREADSHEET_ID)
                            else:
                                spreadsheet_id = GOOGLE_SHEETS_SPREADSHEET_ID
                        except (AttributeError, KeyError):
                            spreadsheet_id = GOOGLE_SHEETS_SPREADSHEET_ID
                        
                        if spreadsheet_id:
                            sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
                            st.success(f"✅ Logs are permanently stored in Google Sheets")
                            st.caption(f"📊 [Open Google Sheet]({sheet_url}) | Sheet ID: `{spreadsheet_id}`")
                    except:
                        st.info("💡 Logs are stored in Google Sheets (permanent storage)")
                else:
                    if os.path.exists(QA_LOG_FILE):
                        full_path = os.path.abspath(QA_LOG_FILE)
                        file_size = os.path.getsize(QA_LOG_FILE)
                        st.warning(f"⚠️ Logs are stored locally in CSV file (may not persist in Streamlit Cloud)")
                        st.caption(f"📄 File location: `{full_path}` ({file_size} bytes)")
                        st.info("💡 **Tip:** Set up Google Sheets for permanent storage across sessions. See `GOOGLE_SHEETS_SETUP.md`")
                    else:
                        st.warning(f"⚠️ Logs are only in session memory. They will be lost when the session ends.")
                        st.caption(f"💡 **Important:** Set up Google Sheets for permanent storage. See `GOOGLE_SHEETS_SETUP.md`")
                
                # Refresh button to reload from Google Sheets
                if storage_source == "Google Sheets":
                    if st.button("🔄 Refresh from Google Sheets"):
                        try:
                            client = get_google_sheets_client()
                            if client:
                                spreadsheet_id = None
                                sheet_name = GOOGLE_SHEETS_SHEET_NAME
                                try:
                                    if 'google_sheets' in st.secrets:
                                        spreadsheet_id = st.secrets['google_sheets'].get('spreadsheet_id', GOOGLE_SHEETS_SPREADSHEET_ID)
                                        sheet_name = st.secrets['google_sheets'].get('sheet_name', GOOGLE_SHEETS_SHEET_NAME)
                                    else:
                                        spreadsheet_id = GOOGLE_SHEETS_SPREADSHEET_ID
                                except (AttributeError, KeyError):
                                    spreadsheet_id = GOOGLE_SHEETS_SPREADSHEET_ID
                                
                                if spreadsheet_id:
                                    spreadsheet = client.open_by_key(spreadsheet_id)
                                    worksheet = _get_worksheet(spreadsheet, sheet_name)
                                    if worksheet:
                                        records = worksheet.get_all_records()
                                        st.session_state.qa_logs = records
                                        st.success(f"✅ Refreshed! Loaded {len(records)} Q&A pairs from Google Sheets")
                                        st.rerun()
                                    else:
                                        st.error("Could not open worksheet. Check sheet name or use first tab with headers 'question', 'answer'.")
                        except Exception as e:
                            st.error(f"Error refreshing from Google Sheets: {e}")
                
            else:
                st.info("No Q&A pairs logged yet. Ask some questions to start logging!")
                if os.path.exists(QA_LOG_FILE):
                    st.caption(f"Note: Log file exists at `{os.path.abspath(QA_LOG_FILE)}` but is empty or couldn't be loaded.")
            
            st.markdown("")
            if st.button("Close Logs"):
                st.session_state.show_logs = False
                st.rerun()
            st.markdown("---")
        
        # Two columns: Chat and Recommendations
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.header("💬 Ask About Via")
            st.markdown("Ask questions about our services, solutions, and content.")
            
            # Chat interface
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    # Display sources if this is an assistant message with sources
                    if message["role"] == "assistant" and message.get("sources"):
                        st.markdown("---")
                        st.markdown("**Sources:**")
                        for article in message["sources"]:
                            col1, col2 = st.columns([1, 3])
                            with col1:
                                if article.get('thumbnail'):
                                    try:
                                        st.image(article['thumbnail'], width=100)
                                    except:
                                        st.write("")  # Empty space if image fails to load
                                else:
                                    st.write("")  # Empty space if no thumbnail
                            with col2:
                                st.markdown(f"**{article['title']}**")
                                if article.get('description'):
                                    st.caption(article['description'][:150] + "...")
                                st.markdown(f"[Read more →]({article['url']})")
            
            # Chat input
            if prompt := st.chat_input("Ask a question about Via..."):
                # Add user message
                st.session_state.chat_history.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)
                
                # Get response
                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        try:
                            if st.session_state.articles:
                                result = query_website_content(prompt, st.session_state.articles, client)
                                # query_website_content already logs the Q&A pair
                                response_text = result.get('answer', '')
                                sources = result.get('sources', [])
                                logged_to_sheets = result.get('logged_to_sheets', False)
                            else:
                                response_text = "I'm sorry, but I don't have access to the website content right now. Please refresh the cache or try again later."
                                sources = []
                                logged_to_sheets = log_qa_pair(prompt, response_text)
                            
                            st.markdown(response_text)
                            
                            # Display sources if available
                            if sources:
                                st.markdown("---")
                                st.markdown("**Sources:**")
                                for article in sources:
                                    col1, col2 = st.columns([1, 3])
                                    with col1:
                                        if article.get('thumbnail'):
                                            try:
                                                st.image(article['thumbnail'], width=100)
                                            except:
                                                st.write("")  # Empty space if image fails to load
                                        else:
                                            st.write("")  # Empty space if no thumbnail
                                    with col2:
                                        st.markdown(f"**{article['title']}**")
                                        if article.get('description'):
                                            st.caption(article['description'][:150] + "...")
                                        st.markdown(f"[Read more →]({article['url']})")
                            
                            # Store in chat history with sources
                            st.session_state.chat_history.append({
                                "role": "assistant", 
                                "content": response_text,
                                "sources": sources
                            })
                            
                            # Show confirmation: where it was logged
                            log_count = len(st.session_state.get('qa_logs', []))
                            if logged_to_sheets:
                                st.caption(f"✅ Logged to Google Sheets (Total: {log_count} Q&A pairs)")
                            else:
                                st.caption(f"✅ Logged to CSV (Total: {log_count} Q&A pairs)")
                        except Exception as e:
                            error_msg = f"Error: {str(e)}"
                            st.error(error_msg)
                            st.session_state.chat_history.append({
                                "role": "assistant", 
                                "content": error_msg,
                                "sources": []
                            })
                            logged_to_sheets = log_qa_pair(prompt, error_msg)
                            if logged_to_sheets:
                                st.caption("✅ Logged to Google Sheets")
                            else:
                                st.caption("✅ Logged to CSV")
        
        with col2:
            st.header("📚 Recommended Articles")
            st.markdown("Personalized for your profile")
            
            # Get recommendations
            if st.session_state.articles:
                try:
                    recommended = recommend_articles(
                        st.session_state.articles,
                        user_profile['type'],
                        user_profile['state'],
                        client
                    )
                    
                    # Display general articles
                    if recommended.get('general'):
                        st.markdown("### General Content")
                        for i, article in enumerate(recommended['general'], 1):
                            col1, col2 = st.columns([1, 3])
                            with col1:
                                if article.get('thumbnail'):
                                    try:
                                        st.image(article['thumbnail'], width=100)
                                    except:
                                        st.write("")  # Empty space if image fails to load
                                else:
                                    st.write("")  # Empty space if no thumbnail
                            with col2:
                                st.markdown(f"**{i}. {article['title']}**")
                                if article.get('description'):
                                    st.caption(article['description'][:150] + "...")
                                st.markdown(f"[Read more →]({article['url']})")
                            if i < len(recommended['general']):  # Don't add divider after last item
                                st.divider()
                    
                    # Display case studies
                    if recommended.get('general'):  # Add spacing between sections
                        st.markdown("")  # Empty line for spacing
                    st.markdown("### Case Studies & Success Stories")
                    if recommended.get('case_studies'):
                        for i, article in enumerate(recommended['case_studies'], 1):
                            col1, col2 = st.columns([1, 3])
                            with col1:
                                if article.get('thumbnail'):
                                    try:
                                        st.image(article['thumbnail'], width=100)
                                    except:
                                        st.write("")  # Empty space if image fails to load
                                else:
                                    st.write("")  # Empty space if no thumbnail
                            with col2:
                                st.markdown(f"**{i}. {article['title']}**")
                                if article.get('description'):
                                    st.caption(article['description'][:150] + "...")
                                st.markdown(f"[Read more →]({article['url']})")
                            if i < len(recommended['case_studies']):  # Don't add divider after last item
                                st.divider()
                    else:
                        st.info("No geographically relevant case studies found for your location. Check back later or browse all case studies on our website.")
                except Exception as e:
                    st.error(f"Error getting recommendations: {e}")
            else:
                st.warning("No articles loaded. Please refresh the cache or check your connection.")

if __name__ == "__main__":
    main()
