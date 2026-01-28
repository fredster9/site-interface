# Via Web App - Personalized Content Interface

A Streamlit web application for ridewithvia.com that provides personalized content recommendations and an LLM-powered chat interface.

## Features

- **User Profile Collection**: Collects user type (city/transit agency) and location (state) for personalized content
- **Semantic Search**: Uses OpenAI embeddings for intelligent article matching based on meaning, not just keywords
- **Personalized Recommendations**: 
  - 3 general content articles
  - 2 geographically relevant case studies/success stories
- **LLM Chat Interface**: Ask questions about Via's services and get answers based on website content
- **Content Caching**: Automatically scrapes and caches website content for fast access
- **Thumbnail Images**: Displays article thumbnails in recommendations

## Setup

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create `openai_secrets.json` with your OpenAI API key (for local development):
```json
{
  "openai_api_key": "your-api-key-here"
}
```

3. Run the app locally (choose one method):

**Option A: Using the run script (recommended)**
```bash
./run_local.sh
```

**Option B: Direct Streamlit command**
```bash
python3 -m streamlit run via_web_app.py
```

**Note:** If you get a "command not found" error, make sure Streamlit is installed:
```bash
pip install -r requirements.txt
```

If you're using a virtual environment, activate it first:
```bash
# Create virtual environment (if needed)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python3 -m streamlit run via_web_app.py
```

The app will open in your browser at `http://localhost:8501`. Test your changes locally before pushing to GitHub!

### Streamlit Cloud Deployment

1. Push code to GitHub repository
2. Connect repository to Streamlit Cloud
3. Add secrets in Streamlit Cloud dashboard:
   - Go to app settings → Secrets
   - Add:
   ```toml
   [openai]
   api_key = "your-openai-api-key-here"
   ```
   Or alternatively:
   ```toml
   OPENAI_API_KEY = "your-openai-api-key-here"
   ```
4. Deploy!

## Configuration

- **Content Sources**: The app scrapes content from:
  - `/audience/`
  - `/solutions/`
  - `/resources/`
  - `/blog/`
  - `/case-studies/`
  
- **Cache**: Content is cached in `via_website_content.json` after first scrape. Use the "🔄 Refresh Cache" button to rebuild.

## Files

- `via_web_app.py` - Main Streamlit application
- `export_cache_list.py` - Utility to export cached articles to a text file
- `requirements.txt` - Python dependencies
- `.streamlit/config.toml` - Streamlit configuration

## Technology Stack

- **Streamlit** - Web framework
- **OpenAI** - GPT-4 for chat, embeddings for semantic search
- **BeautifulSoup** - Web scraping
- **NumPy** - Cosine similarity calculations
