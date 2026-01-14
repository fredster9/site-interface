"""
Export cached articles to a readable text file.
Run this script to see all articles in the cache.
"""

import json
import os
from datetime import datetime

CONTENT_CACHE_FILE = 'via_website_content.json'
OUTPUT_FILE = f'cached_articles_list_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'

def export_cache_to_file():
    """Export the cached articles to a readable text file."""
    if not os.path.exists(CONTENT_CACHE_FILE):
        print(f"❌ Cache file not found: {CONTENT_CACHE_FILE}")
        print("   The cache will be created when you first run the Streamlit app.")
        return
    
    try:
        with open(CONTENT_CACHE_FILE, 'r') as f:
            articles = json.load(f)
        
        print(f"📚 Found {len(articles)} articles in cache")
        print(f"📝 Exporting to {OUTPUT_FILE}...")
        
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("VIA WEBSITE CONTENT CACHE - ARTICLE LIST\n")
            f.write("=" * 80 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Articles: {len(articles)}\n")
            f.write("=" * 80 + "\n\n")
            
            # Group by type
            by_type = {}
            for article in articles:
                article_type = article.get('type', 'unknown')
                if article_type not in by_type:
                    by_type[article_type] = []
                by_type[article_type].append(article)
            
            # Write summary by type
            f.write("SUMMARY BY TYPE\n")
            f.write("-" * 80 + "\n")
            for article_type, type_articles in sorted(by_type.items()):
                f.write(f"{article_type.upper()}: {len(type_articles)} articles\n")
            f.write("\n" + "=" * 80 + "\n\n")
            
            # Write detailed list
            for idx, article in enumerate(articles, 1):
                f.write(f"\n{'=' * 80}\n")
                f.write(f"ARTICLE #{idx}\n")
                f.write(f"{'=' * 80}\n")
                f.write(f"Type: {article.get('type', 'N/A')}\n")
                f.write(f"Title: {article.get('title', 'N/A')}\n")
                f.write(f"URL: {article.get('url', 'N/A')}\n")
                if article.get('description'):
                    f.write(f"Description: {article.get('description')}\n")
                if article.get('states'):
                    f.write(f"States Mentioned: {', '.join(article.get('states', []))}\n")
                if article.get('content'):
                    content_preview = article.get('content', '')[:300]
                    f.write(f"Content Preview: {content_preview}...\n")
                f.write("\n")
        
        print(f"✅ Successfully exported to {OUTPUT_FILE}")
        print(f"   You can now review the list and add more sections if needed.")
        
    except Exception as e:
        print(f"❌ Error exporting cache: {e}")

if __name__ == "__main__":
    export_cache_to_file()
